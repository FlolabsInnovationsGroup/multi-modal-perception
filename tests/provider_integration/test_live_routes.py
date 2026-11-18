"""T5.4: credentialed routes /invoke, /transcribe and /validate.

End to end through FastAPI with the live token checker and credential reader,
both talking to a simulated backend over httpx.MockTransport. Provider calls go
to a scripted adapter, or to the real OpenAI adapter over a mocked transport.
Offline only; synthetic keys and tokens.
"""

import logging
import os
import unittest
from unittest import mock

import httpx
from fastapi import FastAPI

import main
from api import provider_routes
from api.provider_routes import LiveRoute, create_router
from services.provider_integration import LOCAL_LIMIT_PROFILE, Operation, Target
from services.provider_integration.adapters.openai import OpenAIAdapter
from services.provider_integration.config import ModuleConfig
from services.provider_integration.handler import Handler
from services.provider_integration.http_contract import MESSAGES
from services.provider_integration.errors import ErrorCode
from services.provider_integration.live.reader import BackendCredentialReader
from services.provider_integration.live.verifier import JwksClient, JwtContextVerifier
from services.provider_integration.orchestrator import Orchestrator

from fakes import ScriptedAdapter, make_provider_config, network_guard_patchers
from live_fixtures import (
    BINDING,
    GENERATE,
    NOW,
    PROVIDER_KEY,
    SERVICE_SECRET,
    Clock,
    FakeBackend,
    SigningKey,
    body_json,
    settings,
    wall,
)
from test_openai_adapter import Recorder, chat_response, transcription_response

GEN = Target(Operation.GENERATE_TEXT, "gpt-4o-mini")
TR = Target(Operation.TRANSCRIBE_AUDIO, "gpt-4o-mini-transcribe")
BOTH = frozenset({GEN, TR})
AUDIO = b"RIFF-synthetic-audio-bytes"
_patches = []


def setUpModule():
    for patcher in network_guard_patchers():
        patcher.start()
        _patches.append(patcher)


def tearDownModule():
    while _patches:
        _patches.pop().stop()


class RouteRig:
    def __init__(self, adapter=None, configured=True):
        self.key = SigningKey("key-1")
        self.backend = FakeBackend([self.key])
        self.backend.resolve_ok()
        self.adapter = adapter or ScriptedAdapter(BOTH)
        live_settings = settings()
        jwks = JwksClient(live_settings, transport=self.backend.transport(), clock=Clock(1000.0))
        self.verifier = JwtContextVerifier(live_settings, jwks=jwks, wall_clock=wall(NOW))
        orchestrator = Orchestrator(
            config=ModuleConfig(limits=LOCAL_LIMIT_PROFILE, providers={"openai": make_provider_config()}),
            reader=BackendCredentialReader(live_settings, transport=self.backend.transport()),
            adapters={"openai": self.adapter},
        )
        self.orchestrator = orchestrator
        handler = Handler(verifier=self.verifier, orchestrator=orchestrator, limits=LOCAL_LIMIT_PROFILE)
        live = LiveRoute(handler=handler, verifier=self.verifier, limits=LOCAL_LIMIT_PROFILE)
        self.app = FastAPI()
        self.app.include_router(create_router(lambda: live if configured else None))

    def token(self, **claims):
        return self.key.token(NOW, **claims)

    async def call(self, path, *, token=None, headers=None, **kwargs):
        all_headers = dict(headers or {})
        if token is not None:
            all_headers["Authorization"] = f"Bearer {token}"
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://multimodal.test") as client:
            return await client.post(path, headers=all_headers, **kwargs)


class RouteTestCase(unittest.IsolatedAsyncioTestCase):
    def assertError(self, response, status, code, *secrets):
        self.assertEqual(response.status_code, status, response.text)
        body = response.json()
        self.assertEqual(set(body), {"error_code", "message", "request_id"})
        self.assertEqual(body["error_code"], code.value)
        self.assertEqual(body["message"], MESSAGES[code])
        for secret in (PROVIDER_KEY, SERVICE_SECRET, *secrets):
            self.assertNotIn(secret, response.text)


class InvokeTests(RouteTestCase):
    async def test_invoke_success_uses_the_resolved_key(self):
        rig = RouteRig()
        token = rig.token(jti="req-invoke-1")
        response = await rig.call("/invoke", token=token, json={"text": "Hello", "generation_model": "gpt-4o-mini"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"result": "Synthetic answer", "model": "gpt-4o-mini", "file_type": "text",
                                           "total_tokens": None, "provider_request_id": None, "request_id": "req-invoke-1"})
        self.assertEqual([call.key for call in rig.adapter.calls], [PROVIDER_KEY])
        self.assertEqual([body_json(r) for r in rig.backend.resolve_requests()], [{"context_token": token}])
        self.assertNotIn(token, response.text)

    async def test_end_to_end_with_real_openai_adapter(self):
        recorder = Recorder(chat_response("Real adapter answer", request_id="req_chat_9"))
        adapter = OpenAIAdapter(BOTH, connect_timeout_seconds=5,
                                max_response_bytes=LOCAL_LIMIT_PROFILE.max_response_body_bytes,
                                transport=recorder.transport())
        rig = RouteRig(adapter=adapter)
        response = await rig.call("/invoke", token=rig.token(), json={"text": "Hello", "generation_model": "gpt-4o-mini"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["result"], body["provider_request_id"]), ("Real adapter answer", "req_chat_9"))
        self.assertIsInstance(body["total_tokens"], int)
        self.assertEqual(recorder.requests[0].headers["authorization"], f"Bearer {PROVIDER_KEY}")

    async def test_missing_or_bad_token_is_401_and_body_is_not_read(self):
        rig = RouteRig()
        stranger = SigningKey("key-1")
        cases = {"no header": None, "not a jwt": "abc", "wrong signer": stranger.token(NOW),
                 "expired": rig.key.token(NOW - 500), "wrong audience": rig.token(aud="someone-else")}
        for name, token in cases.items():
            with self.subTest(case=name):
                response = await rig.call("/invoke", token=token, json={"text": "Hello", "generation_model": "gpt-4o-mini"})
                self.assertError(response, 401, ErrorCode.ACCESS_DENIED, *(t for t in [token] if t))
        self.assertEqual(rig.backend.resolve_requests(), [])
        self.assertEqual(rig.adapter.calls, [])

    async def test_body_is_not_read_before_the_token_is_verified(self):
        rig = RouteRig()
        received, sent = [], []

        async def receive():
            received.append(True)
            return {"type": "http.request", "body": b"{}", "more_body": False}

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
                 "path": "/transcribe", "raw_path": b"/transcribe", "root_path": "", "query_string": b"",
                 "headers": [(b"host", b"multimodal.test"), (b"authorization", b"Bearer forged.token.value"),
                             (b"content-type", b"multipart/form-data; boundary=x"), (b"content-length", b"10485760")],
                 "client": ("203.0.113.9", 4000), "server": ("multimodal.test", 80)}
        await rig.app(scope, receive, send)
        self.assertEqual(received, [])
        self.assertEqual(sent[0]["status"], 401)

    async def test_model_outside_token_is_denied_and_unapproved_model_unsupported(self):
        rig = RouteRig()
        narrow = rig.token(targets=[dict(GENERATE)])
        response = await rig.call("/invoke", token=narrow, json={"text": "Hi", "generation_model": "gpt-other"})
        self.assertError(response, 403, ErrorCode.ACCESS_DENIED)
        wide = rig.token(targets=[dict(GENERATE), {"operation": "generate_text", "model": "gpt-unapproved"}])
        response = await rig.call("/invoke", token=wide, json={"text": "Hi", "generation_model": "gpt-unapproved"})
        self.assertError(response, 400, ErrorCode.UNSUPPORTED_OPERATION)
        self.assertEqual(rig.adapter.calls, [])

    async def test_replayed_token_is_refused(self):
        rig = RouteRig()
        token = rig.token()
        first = await rig.call("/invoke", token=token, json={"text": "Hi", "generation_model": "gpt-4o-mini"})
        second = await rig.call("/invoke", token=token, json={"text": "Hi", "generation_model": "gpt-4o-mini"})
        self.assertEqual(first.status_code, 200)
        self.assertError(second, 403, ErrorCode.ACCESS_DENIED)
        self.assertEqual(len(rig.backend.resolve_requests()), 1)

    async def test_bad_bodies_are_400(self):
        rig = RouteRig()
        cases = {"not json": dict(content=b"{oops", headers={"content-type": "application/json"}),
                 "array": dict(json=["Hello"]),
                 "unknown field": dict(json={"text": "Hi", "generation_model": "gpt-4o-mini", "api_key": "x"}),
                 "missing model": dict(json={"text": "Hi"}),
                 "audio in json": dict(json={"text": "Hi", "generation_model": "gpt-4o-mini", "audio": "AAAA"}),
                 "too large": dict(content=b"{" + b" " * (600 * 1024) + b"}", headers={"content-type": "application/json"})}
        for name, kwargs in cases.items():
            with self.subTest(case=name):
                response = await rig.call("/invoke", token=rig.token(), **kwargs)
                self.assertError(response, 400, ErrorCode.INVALID_INPUT)
        self.assertEqual(rig.adapter.calls, [])

    async def test_backend_refusals_map_to_safe_errors(self):
        for status, code, http_status in ((409, ErrorCode.CREDENTIAL_UNAVAILABLE, 403),
                                          (403, ErrorCode.ACCESS_DENIED, 403),
                                          (503, ErrorCode.CREDENTIAL_UNAVAILABLE, 403)):
            with self.subTest(backend_status=status):
                rig = RouteRig()
                rig.backend.resolve_status = status
                rig.backend.resolve_body = {"error": f"version disabled {PROVIDER_KEY}"}
                response = await rig.call("/invoke", token=rig.token(), json={"text": "Hi", "generation_model": "gpt-4o-mini"})
                self.assertError(response, http_status, code)
                self.assertEqual(rig.adapter.calls, [])


class TranscribeTests(RouteTestCase):
    def multipart(self, **overrides):
        data = {"audio_format": "wav", "transcription_model": "gpt-4o-mini-transcribe", "generation_model": "gpt-4o-mini"}
        data.update({k: v for k, v in overrides.items() if k != "audio"})
        files = {"audio": ("speech.wav", overrides.get("audio", AUDIO), "audio/wav")}
        return dict(data={k: v for k, v in data.items() if v is not None}, files=files)

    async def test_transcribe_success_in_memory(self):
        rig = RouteRig()
        with mock.patch("python_multipart.multipart.tempfile.NamedTemporaryFile", side_effect=AssertionError("disk")), \
             mock.patch("starlette.formparsers.SpooledTemporaryFile", side_effect=AssertionError("disk")):
            response = await rig.call("/transcribe", token=rig.token(), **self.multipart(text="Summarize"))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["file_type"], "audio")
        self.assertEqual([call.operation for call in rig.adapter.calls], ["transcribe_audio", "generate_text"])
        self.assertEqual(rig.adapter.calls[0].audio_length, len(AUDIO))

    async def test_large_audio_stays_in_memory(self):
        rig = RouteRig()
        big = b"\x01" * (2 * 1024 * 1024)  # larger than the framework's 1 MiB spool threshold
        with mock.patch("python_multipart.multipart.tempfile.NamedTemporaryFile", side_effect=AssertionError("disk")):
            response = await rig.call("/transcribe", token=rig.token(), **self.multipart(audio=big))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(rig.adapter.calls[0].audio_length, len(big))

    async def test_bad_uploads_are_400(self):
        rig = RouteRig()
        too_big = b"\x00" * (LOCAL_LIMIT_PROFILE.max_audio_bytes + 300 * 1024)
        cases = {
            "missing format": self.multipart(audio_format=None),
            "missing transcription model": self.multipart(transcription_model=None),
            "unknown field": self.multipart(api_key="x"),
            "bad format": self.multipart(audio_format="flac"),
            "too large": self.multipart(audio=too_big),
        }
        for name, kwargs in cases.items():
            with self.subTest(case=name):
                response = await rig.call("/transcribe", token=rig.token(), **kwargs)
                self.assertError(response, 400, ErrorCode.INVALID_INPUT)
        no_audio = await rig.call("/transcribe", token=rig.token(), data={"audio_format": "wav", "generation_model": "gpt-4o-mini"})
        self.assertError(no_audio, 400, ErrorCode.INVALID_INPUT)
        as_json = await rig.call("/transcribe", token=rig.token(), json={"audio": "AAAA"})
        self.assertError(as_json, 400, ErrorCode.INVALID_INPUT)
        self.assertEqual(rig.adapter.calls, [])


class ValidateTests(RouteTestCase):
    async def test_validate_returns_version_bound_result(self):
        rig = RouteRig()
        rig.backend.resolve_ok(state="pending")
        token = rig.token(kind="validate", targets=[dict(GENERATE)], jti="req-validate-1")
        response = await rig.call("/validate", token=token, json={"operation": "generate_text", "model": "gpt-4o-mini"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body["status"], body["reason_code"], body["credential_version"], body["request_id"]),
                         ("valid", None, "v1", "req-validate-1"))
        self.assertTrue(body["checked_at"].endswith("Z"))
        self.assertEqual([call.operation for call in rig.adapter.calls], ["validate_access"])

    async def test_invoke_token_cannot_validate_and_validate_token_cannot_invoke(self):
        rig = RouteRig()
        response = await rig.call("/validate", token=rig.token(), json={"operation": "generate_text", "model": "gpt-4o-mini"})
        self.assertError(response, 403, ErrorCode.ACCESS_DENIED)
        validate_token = rig.token(kind="validate", targets=[dict(GENERATE)])
        response = await rig.call("/invoke", token=validate_token, json={"text": "Hi", "generation_model": "gpt-4o-mini"})
        self.assertError(response, 403, ErrorCode.ACCESS_DENIED)
        self.assertEqual(rig.adapter.calls, [])


class ConfigurationAndLeakTests(RouteTestCase):
    async def test_unconfigured_routes_answer_503_without_reading_anything(self):
        rig = RouteRig(configured=False)
        for path in ("/invoke", "/transcribe", "/validate"):
            with self.subTest(path=path):
                response = await rig.call(path, token=rig.token(), json={})
                self.assertError(response, 503, ErrorCode.NOT_CONFIGURED)
        self.assertEqual(rig.backend.requests, [])

    async def test_main_app_serves_routes_and_fails_closed_without_settings(self):
        names = ("FLOBRAIN_BACKEND_URL", "MULTIMODAL_SERVICE_SECRET", "CREDENTIAL_JWT_ISSUER",
                 "CREDENTIAL_JWT_AUDIENCE", "PROVIDER_APPROVED_TARGETS")
        env = {k: v for k, v in os.environ.items() if k not in names}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertIsNone(provider_routes.build_from_environment(os.environ))
            transport = httpx.ASGITransport(app=main.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://multimodal.test") as client:
                response = await client.post("/invoke", json={"text": "Hi", "generation_model": "gpt-4o-mini"},
                                             headers={"Authorization": "Bearer x.y.z"})
        self.assertError(response, 503, ErrorCode.NOT_CONFIGURED)

    async def test_nothing_secret_reaches_logs(self):
        rig = RouteRig()
        token = rig.token()
        with self.assertLogs(level=logging.DEBUG) as captured:
            logging.getLogger("routes-test").debug("marker")
            await rig.call("/invoke", token=token, json={"text": "Hi", "generation_model": "gpt-4o-mini"})
            rig.backend.resolve_status = 409
            await rig.call("/invoke", token=rig.token(), json={"text": "Hi", "generation_model": "gpt-4o-mini"})
        joined = "\n".join(captured.output)
        for secret in (PROVIDER_KEY, SERVICE_SECRET, token):
            self.assertNotIn(secret, joined)


if __name__ == "__main__":
    unittest.main()


class ReviewFixRouteTests(RouteTestCase):
    """Independent review findings of 2026-11-18 (fixes 2 and 3)."""

    async def raw_post(self, rig, path, token):
        received, sent = [], []

        async def receive():
            received.append(True)
            return {"type": "http.request", "body": b"{}", "more_body": False}

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
                 "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"",
                 "headers": [(b"host", b"multimodal.test"), (b"authorization", f"Bearer {token}".encode()),
                             (b"content-type", b"application/json"), (b"content-length", b"2")],
                 "client": ("203.0.113.9", 4000), "server": ("multimodal.test", 80)}
        await rig.app(scope, receive, send)
        return received, sent[0]["status"]

    async def test_reused_or_wrong_kind_token_is_refused_before_reading(self):
        rig = RouteRig()
        token = rig.token()
        first = await rig.call("/invoke", token=token, json={"text": "Hi", "generation_model": "gpt-4o-mini"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(await self.raw_post(rig, "/invoke", token), ([], 403))
        validate_token = rig.token(kind="validate", targets=[dict(GENERATE)])
        self.assertEqual(await self.raw_post(rig, "/transcribe", validate_token), ([], 403))
        self.assertEqual(len(rig.backend.resolve_requests()), 1)

    async def test_deeply_nested_json_is_a_normal_400(self):
        rig = RouteRig()
        response = await rig.call("/invoke", token=rig.token(), content=b"[" * 100_000,
                                  headers={"content-type": "application/json"})
        self.assertError(response, 400, ErrorCode.INVALID_INPUT)

    async def test_requests_in_flight_are_capped(self):
        import asyncio
        import dataclasses
        from fakes import PauseGate, Script

        rig = RouteRig()
        limits = dataclasses.replace(LOCAL_LIMIT_PROFILE, max_concurrent_operations=1)
        gate = PauseGate()
        rig.adapter.scripts["generate_text"].append(Script(gate=gate))
        live = LiveRoute(handler=Handler(verifier=rig.verifier, orchestrator=rig.orchestrator, limits=limits),
                         verifier=rig.verifier, limits=limits)
        app = FastAPI()
        app.include_router(create_router(lambda: live))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://multimodal.test") as client:
            first = asyncio.create_task(client.post("/invoke", json={"text": "Hi", "generation_model": "gpt-4o-mini"},
                                                    headers={"Authorization": f"Bearer {rig.token()}"}))
            await asyncio.wait_for(gate.entered.wait(), timeout=5)
            second = await client.post("/invoke", json={"text": "Hi", "generation_model": "gpt-4o-mini"},
                                       headers={"Authorization": f"Bearer {rig.token()}"})
            gate.release.set()
            first_response = await first
        self.assertError(second, 429, ErrorCode.CAPACITY_EXCEEDED)
        self.assertEqual(first_response.status_code, 200)

