"""T3.1 OpenAI adapter tests: the real SDK over httpx.MockTransport, offline.

Replaces the 4 draft tests from commit f7fde62 (Sukhpreet); her status cases
are kept in the error matrix below. Requires the project .venv (openai, httpx).
"""

import asyncio
import json
import logging
import os
import pathlib
import traceback
import unittest
from unittest import mock

import httpx

from services.provider_integration import (
    AudioFormat,
    Binding,
    CredentialLease,
    CredentialSource,
    CredentialState,
    ErrorCode,
    Operation,
    ProviderAdapter,
    ProviderIntegrationError,
    ProviderOperationError,
    ProviderSession,
    SecretValue,
    StepOutput,
    Target,
    UsageEntry,
)
from services.provider_integration.adapters import openai as adapter_module
from services.provider_integration.adapters.openai import OpenAIAdapter, classify_error

from fakes import (
    BOTH_TARGETS,
    GENERATE_TARGET,
    KEY_SCOPE_A,
    SYNTHETIC_DESTINATION,
    TRANSCRIBE_TARGET,
    make_provider_config,
    network_guard_patchers,
)

BODY_CANARY = "provider-body-canary-do-not-retain"
ENV_KEY_CANARY = "test-provider-key-environment-canary"
ADAPTER_SOURCE = pathlib.Path(adapter_module.__file__)
_patches = []


def setUpModule():
    for patcher in network_guard_patchers():
        patcher.start()
        _patches.append(patcher)


def tearDownModule():
    while _patches:
        _patches.pop().stop()


def make_lease(provider="openai", key=KEY_SCOPE_A, targets=BOTH_TARGETS):
    return CredentialLease(
        binding=Binding("scope-A", "credential-A", "v1", CredentialSource.CUSTOMER, provider),
        state=CredentialState.ACTIVE,
        secret=SecretValue(key),
        permitted_targets=targets,
        admission_id="admission-1",
    )


def chat_response(content="Synthetic answer", usage=True, request_id="req_chat_1", status=200):
    body = {
        "id": "chatcmpl-synthetic",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
    }
    if usage:
        body["usage"] = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    headers = {"x-request-id": request_id} if request_id else {}
    return httpx.Response(status, json=body, headers=headers)


def transcription_response(text="synthetic transcript", usage=None, request_id="req_stt_1"):
    body = {"text": text}
    if usage is not None:
        body["usage"] = usage
    return httpx.Response(200, json=body, headers={"x-request-id": request_id})


def error_response(status, code=None, error_type=None, headers=None):
    body = {"error": {"message": f"{BODY_CANARY} {KEY_SCOPE_A}", "type": error_type, "code": code, "param": None}}
    return httpx.Response(status, json=body, headers={"x-request-id": "req_err_1", **(headers or {})})


class Recorder:
    """MockTransport handler that records requests and replays scripted responses."""

    def __init__(self, *responses):
        self.requests = []
        self._responses = list(responses)

    def __call__(self, request):
        request.read()
        self.requests.append(request)
        item = self._responses.pop(0) if self._responses else chat_response()
        if isinstance(item, BaseException):
            raise item
        return item

    def transport(self):
        return httpx.MockTransport(self)


class CapturingClient(httpx.AsyncClient):
    """Real httpx.AsyncClient subclass that records construction kwargs (SDK isinstance checks still pass)."""

    created = []

    def __init__(self, *args, **kwargs):
        CapturingClient.created.append((self, kwargs))
        super().__init__(*args, **kwargs)


def capture_clients():
    CapturingClient.created = []
    return mock.patch.object(adapter_module.httpx, "AsyncClient", CapturingClient)


MAX_RESPONSE_BYTES = 1_048_576


def make_adapter(recorder, targets=BOTH_TARGETS, max_response_bytes=MAX_RESPONSE_BYTES):
    return OpenAIAdapter(
        targets, connect_timeout_seconds=5, max_response_bytes=max_response_bytes, transport=recorder.transport()
    )


class AdapterTestCase(unittest.IsolatedAsyncioTestCase):
    def assertNoSecrets(self, *rendered):
        for text in rendered:
            self.assertNotIn(KEY_SCOPE_A, text)
            self.assertNotIn(BODY_CANARY, text)
            self.assertNotIn(ENV_KEY_CANARY, text)

    async def generate(self, recorder, text="Hello", target=GENERATE_TARGET, lease=None, config=None):
        adapter = make_adapter(recorder)
        async with adapter.open_session(lease or make_lease(), config or make_provider_config()) as session:
            return await session.generate_text(target, text, 5.0)


class PortAndCapabilityTests(AdapterTestCase):
    async def test_selected_models(self):
        """TC-01 (adapter): only configured pairs; unsupported targets send nothing."""
        recorder = Recorder()
        adapter = make_adapter(recorder, targets=frozenset({GENERATE_TARGET}))
        self.assertIsInstance(adapter, ProviderAdapter)
        self.assertEqual(adapter.supported_operations(), frozenset({GENERATE_TARGET}))
        async with adapter.open_session(make_lease(), make_provider_config()) as session:
            self.assertIsInstance(session, ProviderSession)
            for call in (
                session.generate_text(Target(Operation.GENERATE_TEXT, "gpt-4o"), "Hello", 5.0),
                session.generate_text(TRANSCRIBE_TARGET, "Hello", 5.0),
                session.transcribe_audio(TRANSCRIBE_TARGET, b"\x01", AudioFormat.WAV, 5.0),
            ):
                with self.subTest(call=call.__qualname__), self.assertRaises(ProviderIntegrationError) as caught:
                    await call
                self.assertIs(caught.exception.code, ErrorCode.UNSUPPORTED_OPERATION)
        narrow_lease = make_lease(targets=frozenset({TRANSCRIBE_TARGET}))
        async with make_adapter(recorder).open_session(narrow_lease, make_provider_config()) as session:
            with self.assertRaises(ProviderIntegrationError):
                await session.generate_text(GENERATE_TARGET, "Hello", 5.0)
        self.assertEqual(recorder.requests, [])

    def test_constructor_requires_explicit_configuration(self):
        for targets in (frozenset(), {GENERATE_TARGET}, frozenset({"generate_text"})):
            with self.subTest(targets=type(targets).__name__), self.assertRaises(ValueError):
                OpenAIAdapter(targets, connect_timeout_seconds=5, max_response_bytes=MAX_RESPONSE_BYTES)
        for timeout in (0, -1, float("nan"), True, None):
            with self.subTest(timeout=repr(timeout)), self.assertRaises(ValueError):
                OpenAIAdapter(BOTH_TARGETS, connect_timeout_seconds=timeout, max_response_bytes=MAX_RESPONSE_BYTES)
        for limit in (0, -1, 1.5, True, None):
            with self.subTest(max_response_bytes=repr(limit)), self.assertRaises(ValueError):
                OpenAIAdapter(BOTH_TARGETS, connect_timeout_seconds=5, max_response_bytes=limit)
        with self.assertRaises(TypeError):
            OpenAIAdapter(BOTH_TARGETS, connect_timeout_seconds=5)  # no implicit response cap
        with self.assertRaises(TypeError):
            OpenAIAdapter(BOTH_TARGETS, connect_timeout_seconds=5, max_response_bytes=MAX_RESPONSE_BYTES, transport=object())

    async def test_wrong_provider_or_bad_inputs_fail_before_sending(self):
        recorder = Recorder()
        for lease, config in (
            (make_lease(provider="other-provider"), make_provider_config()),
            (make_lease(), make_provider_config(provider="other-provider")),
        ):
            with self.subTest(provider=lease.binding.provider + "/" + config.provider):
                with self.assertRaises(ProviderIntegrationError) as caught:
                    async with make_adapter(recorder).open_session(lease, config):
                        self.fail("session should not open")
                self.assertIs(caught.exception.code, ErrorCode.NOT_CONFIGURED)
        async with make_adapter(recorder).open_session(make_lease(), make_provider_config()) as session:
            for call, code in (
                (session.generate_text(GENERATE_TARGET, "", 5.0), ErrorCode.INVALID_INPUT),
                (session.generate_text(GENERATE_TARGET, "Hello", 0), ErrorCode.OPERATION_TIMEOUT),
                (session.transcribe_audio(TRANSCRIBE_TARGET, b"", AudioFormat.WAV, 5.0), ErrorCode.INVALID_INPUT),
                (session.transcribe_audio(TRANSCRIBE_TARGET, b"\x01", "wav", 5.0), ErrorCode.INVALID_INPUT),
            ):
                with self.subTest(code=code.value), self.assertRaises(ProviderIntegrationError) as caught:
                    await call
                self.assertIs(caught.exception.code, code)
        self.assertEqual(recorder.requests, [])

    async def test_validation_probe_now_implemented(self):
        """A6 superseded by T3.2: validate_access sends exactly one probe (details in test_openai_validation)."""
        recorder = Recorder(chat_response(content="OK"))
        async with make_adapter(recorder).open_session(make_lease(), make_provider_config()) as session:
            outcome = await session.validate_access(GENERATE_TARGET, 5.0)
        self.assertEqual(outcome.status.value, "valid")
        self.assertEqual(len(recorder.requests), 1)
        async with make_adapter(recorder).open_session(make_lease(), make_provider_config()) as session:
            with self.assertRaises(ProviderIntegrationError) as caught:
                await session.validate_access(Target(Operation.GENERATE_TEXT, "gpt-4o"), 5.0)
        self.assertIs(caught.exception.code, ErrorCode.UNSUPPORTED_OPERATION)
        self.assertEqual(len(recorder.requests), 1)


class RequestShapeTests(AdapterTestCase):
    async def test_generation_request_shape(self):
        recorder = Recorder(chat_response())
        output = await self.generate(recorder, text="Hello there")
        self.assertIsInstance(output, StepOutput)
        self.assertEqual(output.text, "Synthetic answer")
        self.assertEqual(
            output.usage,
            UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini", input_tokens=10, output_tokens=5,
                       total_tokens=15, provider_request_id="req_chat_1"),
        )
        self.assertEqual(len(recorder.requests), 1)
        request = recorder.requests[0]
        self.assertEqual((request.method, str(request.url)), ("POST", SYNTHETIC_DESTINATION + "chat/completions"))
        self.assertEqual(request.headers["authorization"], f"Bearer {KEY_SCOPE_A}")
        body = json.loads(request.content)
        self.assertEqual(body["model"], "gpt-4o-mini")
        self.assertEqual(body["messages"], [
            {"role": "system", "content": "Synthetic system prompt."},
            {"role": "user", "content": "Hello there"},
        ])
        self.assertEqual((body["max_tokens"], body["temperature"], body["store"]), (256, 0.4, False))
        self.assertIn(body.get("stream"), (False, None))
        self.assertNotIn("tools", body)

    async def test_transcription_request_shape(self):
        recorder = Recorder(transcription_response(usage={"type": "tokens", "input_tokens": 12, "output_tokens": 4, "total_tokens": 16}))
        adapter = make_adapter(recorder)
        async with adapter.open_session(make_lease(), make_provider_config()) as session:
            output = await session.transcribe_audio(TRANSCRIBE_TARGET, b"RIFF-synthetic-audio", AudioFormat.MP3, 5.0)
        self.assertEqual(output.text, "synthetic transcript")
        self.assertEqual((output.usage.input_tokens, output.usage.output_tokens, output.usage.total_tokens), (12, 4, 16))
        self.assertIsNone(output.usage.audio_seconds)
        request = recorder.requests[0]
        self.assertEqual(str(request.url), SYNTHETIC_DESTINATION + "audio/transcriptions")
        self.assertTrue(request.headers["content-type"].startswith("multipart/form-data"))
        content = request.content
        self.assertIn(b'filename="input.mp3"', content)
        self.assertIn(b"RIFF-synthetic-audio", content)
        self.assertIn(b"gpt-4o-mini-transcribe", content)
        self.assertIn(b'name="response_format"', content)
        self.assertIn(b"json", content)

    async def test_transcription_usage_shapes(self):
        cases = [
            ("duration", {"type": "duration", "seconds": 1.5}, (None, None, 1.5)),
            ("absent", None, (None, None, None)),
            ("negative", {"type": "tokens", "input_tokens": -3, "output_tokens": 2, "total_tokens": 2}, (None, 2, None)),
        ]
        for name, usage, (input_tokens, output_tokens, seconds) in cases:
            with self.subTest(usage=name):
                recorder = Recorder(transcription_response(text="", usage=usage))
                async with make_adapter(recorder).open_session(make_lease(), make_provider_config()) as session:
                    output = await session.transcribe_audio(TRANSCRIBE_TARGET, b"\x01\x02", AudioFormat.WAV, 5.0)
                self.assertEqual(output.text, "")  # no speech is a valid transcription
                self.assertEqual((output.usage.input_tokens, output.usage.output_tokens, output.usage.audio_seconds),
                                 (input_tokens, output_tokens, seconds))

    async def test_usage_absent_and_request_id_filtering(self):
        output = await self.generate(Recorder(chat_response(usage=False, request_id=None)))
        self.assertEqual(output.usage, UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini"))
        output = await self.generate(Recorder(chat_response(request_id=f"req-{KEY_SCOPE_A}")))
        self.assertIsNone(output.usage.provider_request_id)
        self.assertEqual(output.usage.input_tokens, 10)

    async def test_no_environment_inheritance(self):
        """TC-07/TC-09 core: env key, base URL, org, project and proxy are never used."""
        env = {
            "OPENAI_API_KEY": ENV_KEY_CANARY,
            "OPENAI_BASE_URL": "https://attacker.example.test/v1",
            "OPENAI_ORG_ID": "org-canary",
            "OPENAI_PROJECT_ID": "proj-canary",
            "HTTPS_PROXY": "http://proxy.example.test:8080",
            "SSL_CERT_FILE": "C:/nonexistent/canary.pem",
        }
        recorder = Recorder(chat_response())
        with mock.patch.dict(os.environ, env), capture_clients():
            await self.generate(recorder)
        created = [kwargs for _, kwargs in CapturingClient.created]
        request = recorder.requests[0]
        self.assertEqual(request.url.host, "provider.example.test")
        self.assertEqual(request.headers["authorization"], f"Bearer {KEY_SCOPE_A}")
        lowered = {name.lower() for name in request.headers}
        self.assertNotIn("openai-organization", lowered)
        self.assertNotIn("openai-project", lowered)
        rendered = str(dict(request.headers))
        for canary in ("org-canary", "proj-canary", ENV_KEY_CANARY, "attacker.example.test", "proxy.example.test"):
            self.assertNotIn(canary, rendered)
        self.assertEqual(len(created), 1)
        self.assertIs(created[0]["trust_env"], False)
        self.assertIs(created[0]["follow_redirects"], False)
        self.assertIs(created[0]["verify"], True)

    async def test_single_attempt_without_sdk_retries(self):
        for response in (
            error_response(500, headers={"x-should-retry": "true"}),
            error_response(429, code="rate_limit_exceeded", error_type="requests", headers={"retry-after": "0"}),
            error_response(503, code="server_is_overloaded", error_type="service_unavailable_error"),
        ):
            with self.subTest(status=response.status_code):
                recorder = Recorder(response, chat_response())
                with self.assertRaises(ProviderOperationError):
                    await self.generate(recorder)
                self.assertEqual(len(recorder.requests), 1)


class ErrorMappingTests(AdapterTestCase):
    async def test_error_mapping_matrix(self):
        """TC-07 (adapter): L6 table with A2; nothing raw retained."""
        cases = [
            ("401 invalid key", error_response(401, "invalid_api_key", "invalid_request_error"), ErrorCode.CREDENTIAL_REJECTED),
            ("401 other", error_response(401, "account_restricted"), ErrorCode.ACCESS_DENIED),
            ("401 no code", error_response(401), ErrorCode.ACCESS_DENIED),
            ("403 region (A2)", error_response(403, "unsupported_country_region_territory"), ErrorCode.ACCESS_DENIED),
            ("404 model", error_response(404, "model_not_found"), ErrorCode.CAPABILITY_DENIED),
            ("404 other", error_response(404), ErrorCode.PROVIDER_RESPONSE_INVALID),
            ("429 legacy quota type", error_response(429, None, "insufficient_quota"), ErrorCode.QUOTA_EXCEEDED),
            ("429 slow down", error_response(429, "slow_down", "rate_limit_error"), ErrorCode.RATE_LIMITED),
            ("429 other", error_response(429, "rate_limit_exceeded"), ErrorCode.RATE_LIMITED),
            ("408", error_response(408), ErrorCode.PROVIDER_UNAVAILABLE),
            ("500", error_response(500), ErrorCode.PROVIDER_UNAVAILABLE),
            ("501", error_response(501), ErrorCode.PROVIDER_UNAVAILABLE),
            ("503", error_response(503, "server_is_overloaded"), ErrorCode.PROVIDER_UNAVAILABLE),
            ("400", error_response(400), ErrorCode.INVALID_INPUT),
            ("413", error_response(413), ErrorCode.INVALID_INPUT),
            ("422", error_response(422), ErrorCode.INVALID_INPUT),
            ("418", error_response(418), ErrorCode.PROVIDER_RESPONSE_INVALID),
            ("302 redirect", httpx.Response(302, headers={"location": "https://attacker.example.test/steal"}), ErrorCode.PROVIDER_RESPONSE_INVALID),
            ("read timeout", httpx.ReadTimeout("synthetic timeout"), ErrorCode.PROVIDER_TIMEOUT),
            ("connect timeout", httpx.ConnectTimeout("synthetic timeout"), ErrorCode.PROVIDER_TIMEOUT),
            ("connection error", httpx.ConnectError(f"cannot connect {BODY_CANARY}"), ErrorCode.PROVIDER_UNAVAILABLE),
            ("malformed success", httpx.Response(200, content=b"not-json " + BODY_CANARY.encode()), ErrorCode.PROVIDER_RESPONSE_INVALID),
            ("missing choices", httpx.Response(200, json={"id": "x", "object": "chat.completion", "choices": []}), ErrorCode.PROVIDER_RESPONSE_INVALID),
        ]
        for code in sorted(adapter_module.QUOTA_CODES):
            cases.append((f"429 {code}", error_response(429, code, "insufficient_quota"), ErrorCode.QUOTA_EXCEEDED))
        for name, response, expected in cases:
            with self.subTest(case=name):
                recorder = Recorder(response)
                with self.assertRaises(ProviderOperationError) as caught:
                    await self.generate(recorder)
                error = caught.exception
                self.assertIs(error.code, expected)
                self.assertEqual(len(recorder.requests), 1)
                self.assertIsNone(error.__cause__)
                self.assertIsInstance(error.usage, UsageEntry)
                self.assertEqual((error.usage.operation, error.usage.model), (Operation.GENERATE_TEXT, "gpt-4o-mini"))
                self.assertNoSecrets(str(error), repr(error), repr(error.usage), "".join(traceback.format_exception(error)))
                if isinstance(response, httpx.Response) and response.status_code >= 400:
                    self.assertEqual(error.usage.provider_request_id, "req_err_1")

    async def test_transcription_errors_and_malformed_success(self):
        for name, response, expected in (
            ("401", error_response(401, "invalid_api_key"), ErrorCode.CREDENTIAL_REJECTED),
            ("timeout", httpx.ReadTimeout("synthetic"), ErrorCode.PROVIDER_TIMEOUT),
            ("no text", httpx.Response(200, json={"usage": {"type": "duration", "seconds": 1}}), ErrorCode.PROVIDER_RESPONSE_INVALID),
        ):
            with self.subTest(case=name):
                recorder = Recorder(response)
                async with make_adapter(recorder).open_session(make_lease(), make_provider_config()) as session:
                    with self.assertRaises(ProviderOperationError) as caught:
                        await session.transcribe_audio(TRANSCRIBE_TARGET, b"\x01", AudioFormat.WAV, 5.0)
                self.assertIs(caught.exception.code, expected)
                self.assertEqual(caught.exception.usage.operation, Operation.TRANSCRIBE_AUDIO)
                self.assertNoSecrets(repr(caught.exception))

    def test_classify_unknown_exception(self):
        self.assertIs(classify_error(RuntimeError(BODY_CANARY)), ErrorCode.INTERNAL_ERROR)

    async def test_refusal_without_content_returns_empty_text(self):
        output = await self.generate(Recorder(chat_response(content=None)))
        self.assertEqual(output.text, "")  # orchestrator turns this into PROVIDER_RESPONSE_INVALID


class LifecycleTests(AdapterTestCase):
    async def test_one_client_per_session_and_always_closed(self):
        recorder = Recorder(chat_response(), chat_response(), error_response(500))
        adapter = make_adapter(recorder)
        with capture_clients():
            first = make_lease(key="test-provider-key-first")
            second = make_lease(key="test-provider-key-second")
            async with adapter.open_session(first, make_provider_config()) as session_one, \
                    adapter.open_session(second, make_provider_config()) as session_two:
                await asyncio.gather(
                    session_one.generate_text(GENERATE_TARGET, "Same prompt", 5.0),
                    session_two.generate_text(GENERATE_TARGET, "Same prompt", 5.0),
                )
                self.assertIsNot(session_one, session_two)
            with self.assertRaises(RuntimeError):
                async with adapter.open_session(make_lease(), make_provider_config()) as session:
                    raise RuntimeError("synthetic failure inside session")
        created = [client for client, _ in CapturingClient.created]
        self.assertEqual(len(created), 3)
        self.assertEqual(len({id(client) for client in created}), 3)
        self.assertTrue(all(client.is_closed for client in created))
        keys = {request.headers["authorization"] for request in recorder.requests}
        self.assertEqual(keys, {"Bearer test-provider-key-first", "Bearer test-provider-key-second"})

    async def test_debug_logging_fails_closed(self):
        """A3: a session never opens while SDK/transport debug logging is on."""
        for name in ("openai", "httpx", "httpcore"):
            with self.subTest(logger=name):
                logger = logging.getLogger(name)
                previous = logger.level
                logger.setLevel(logging.DEBUG)
                try:
                    recorder = Recorder()
                    with self.assertRaises(ProviderIntegrationError) as caught:
                        async with make_adapter(recorder).open_session(make_lease(), make_provider_config()):
                            self.fail("session should not open")
                    self.assertIs(caught.exception.code, ErrorCode.NOT_CONFIGURED)
                    self.assertEqual(recorder.requests, [])
                finally:
                    logger.setLevel(previous)

    def test_adapter_source_has_no_env_defaults_or_global_client(self):
        source = ADAPTER_SOURCE.read_text(encoding="utf-8")
        for token in ("os.environ", "getenv", "dotenv", "DEFAULT_MODEL", "gpt-4o", "base_url: str", "self.api_key"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
