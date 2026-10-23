"""T4.1 handler and wiring tests (TC-02, TC-10, TC-13, TC-14 local part).

Includes the first combined run: handler -> fake verifier/store -> orchestrator
-> real OpenAIAdapter over httpx.MockTransport. Requires the project .venv.
"""

import asyncio
import os
import pathlib
import subprocess
import sys
import unittest
from datetime import timedelta
from unittest import mock

from services.provider_integration import (
    LOCAL_LIMIT_PROFILE,
    Binding,
    BoundaryFailure,
    ContextKind,
    CredentialSource,
    ErrorCode,
    FileType,
    InvocationResult,
    Outcome,
    ValidationResult,
    ValidationStatus,
    VerifiedContext,
    new_request_id,
)
from services.provider_integration.adapters.openai import OpenAIAdapter
from services.provider_integration.handler import Handler, legacy_success
from services.provider_integration.orchestrator import AUDIO_INSTRUCTION, TRANSCRIPT_SEPARATOR, Orchestrator
from services.provider_integration.wiring import build_handler, build_unconfigured

from fakes import (
    BOTH_TARGETS,
    FAST_LIMITS,
    GENERATE_TARGET,
    KEY_SCOPE_A_V2,
    TRANSCRIBE_TARGET,
    FakeContextVerifier,
    Harness,
    PauseGate,
    Script,
    make_provider_config,
    network_guard_patchers,
)
from test_openai_adapter import Recorder, chat_response, error_response, transcription_response

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE_DIR = REPO_ROOT / "services" / "provider_integration"
CANARY = "untrusted-canary-do-not-reflect"
ENV_KEY_CANARY = "test-provider-key-environment-canary"
_patches = []


def setUpModule():
    for patcher in network_guard_patchers():
        patcher.start()
        _patches.append(patcher)


def tearDownModule():
    while _patches:
        _patches.pop().stop()


def binding_fields(**overrides):
    fields = dict(scope_id="scope-A", credential_ref="credential-A", credential_version="v1",
                  credential_source="customer", provider="openai")
    fields.update(overrides)
    return fields


def text_request(text="Hello", **extra):
    return dict(text=text, generation_model="gpt-4o-mini", **extra)


def audio_request(text="", audio=b"\x01\x02\x03", audio_format="wav", **extra):
    return dict(text=text, audio=audio, audio_format=audio_format, generation_model="gpt-4o-mini",
                transcription_model="gpt-4o-mini-transcribe", **extra)


class OrderLog:
    def __init__(self):
        self.events = []


class RecordingVerifier(FakeContextVerifier):
    def __init__(self, clock, log):
        super().__init__(clock)
        self._log = log

    async def verify(self, *args, **kwargs):
        self._log.events.append("verify")
        return await super().verify(*args, **kwargs)


class RecordingReader:
    def __init__(self, inner, log):
        self._inner = inner
        self._log = log

    def admit(self, context, targets):
        self._log.events.append("admit")
        return self._inner.admit(context, targets)


class Rig:
    """Harness + registered evidence + Handler over the scripted adapter."""

    def __init__(self, limits=LOCAL_LIMIT_PROFILE, verifier_factory=None, targets=BOTH_TARGETS):
        self.log = OrderLog()
        self.h = Harness(limits=limits, reader_factory=lambda store: RecordingReader(store, self.log))
        self.verifier = (verifier_factory or (lambda clock: RecordingVerifier(clock, self.log)))(self.h.clock)
        self.handler = Handler(verifier=self.verifier, orchestrator=self.h.orchestrator, limits=limits)
        if isinstance(self.verifier, FakeContextVerifier):
            self.verifier.register("evidence-invoke", self.h.context(targets=targets))
            self.verifier.register("evidence-validate", self.h.context(kind=ContextKind.VALIDATE, targets=targets))


class HandlerTestCase(unittest.IsolatedAsyncioTestCase):
    def assertBoundary(self, result, code):
        self.assertIsInstance(result, BoundaryFailure)
        self.assertIs(result.error_code, code)
        self.assertIsNone(result.result)
        self.assertEqual(result.usage, ())
        self.assertNotIn(CANARY, repr(result))
        self.assertNotIn("scope-B", repr(result))


class UntrustedContextTests(HandlerTestCase):
    async def test_untrusted_context(self):
        """TC-02: unverified or mismatched calls never reach the reader or provider."""
        cases = [
            ("unknown evidence", "evidence-unknown", binding_fields(), None),
            ("unhashable evidence", ["evidence-invoke"], binding_fields(), None),
            ("other scope", "evidence-invoke", binding_fields(scope_id="scope-B"), None),
            ("other credential", "evidence-invoke", binding_fields(credential_ref="credential-B"), None),
            ("other version", "evidence-invoke", binding_fields(credential_version="v2"), None),
            ("other source", "evidence-invoke", binding_fields(credential_source="platform"), None),
            ("other provider", "evidence-invoke", binding_fields(provider="other-provider"), None),
            ("validation evidence used to invoke", "evidence-validate", binding_fields(), None),
            ("revoked", "evidence-invoke", binding_fields(), lambda rig: rig.verifier.revoke("evidence-invoke")),
            ("expired", "evidence-invoke", binding_fields(), lambda rig: rig.h.clock.advance(301)),
        ]
        for name, evidence, binding, prepare in cases:
            with self.subTest(case=name):
                rig = Rig()
                if prepare:
                    prepare(rig)
                result = await rig.handler.process(evidence, binding, text_request())
                self.assertBoundary(result, ErrorCode.ACCESS_DENIED)
                self.assertEqual(rig.log.events, ["verify"])
                self.assertEqual((rig.h.store.admit_calls, rig.h.adapter.calls), (0, []))

    async def test_misbehaving_verifiers_are_denied(self):
        h_probe = Harness()
        other_context = h_probe.context(scope_id="scope-B", credential_ref="credential-B")

        class Raising:
            async def verify(self, *args):
                raise RuntimeError(f"verifier detail {CANARY}")

        class Hanging:
            async def verify(self, *args):
                await asyncio.Event().wait()

        class WrongBinding:
            async def verify(self, *args):
                return other_context

        class NotAContext:
            async def verify(self, *args):
                return {"binding": "scope-A", "authorized": True}

        class WrongKind:
            def __init__(self, clock):
                self.clock = clock

            async def verify(self, call_evidence, binding, kind, targets):
                return VerifiedContext(binding=binding, request_id=new_request_id(), kind=ContextKind.VALIDATE,
                                       allowed_targets=BOTH_TARGETS, expires_at=self.clock.now() + timedelta(minutes=5))

        for name, factory in (
            ("raising", lambda clock: Raising()),
            ("hanging", lambda clock: Hanging()),
            ("wrong binding", lambda clock: WrongBinding()),
            ("not a context", lambda clock: NotAContext()),
            ("wrong kind", WrongKind),
        ):
            with self.subTest(verifier=name):
                rig = Rig(limits=FAST_LIMITS, verifier_factory=factory)
                result = await rig.handler.process("evidence", binding_fields(), text_request())
                self.assertBoundary(result, ErrorCode.ACCESS_DENIED)
                self.assertEqual((rig.h.store.admit_calls, rig.h.adapter.calls), (0, []))

    async def test_parse_failures(self):
        """C1: unknown fields and malformed values are rejected before the verifier runs."""
        bad_requests = [
            text_request(authorized=True),
            text_request(base_url="https://attacker.example.test/v1"),
            text_request(api_key="test-provider-key-injected"),
            text_request(mode="fake"),
            text_request(headers={"OpenAI-Organization": "org-x"}),
            dict(text="Hello"),
            dict(text=123, generation_model="gpt-4o-mini"),
            dict(text_request(), generation_model="bad model"),
            dict(text_request(), generation_model=None),
            text_request(transcription_model="gpt-4o-mini-transcribe"),
            text_request(audio_format="wav"),
            audio_request(audio=bytearray(b"\x01")),
            audio_request(audio_format="WAV"),
            audio_request(audio_format="flac"),
            audio_request(audio_format=None),
            dict(audio_request(), transcription_model=None),
            text_request(text="   "),
            dict(text="", audio=b"", generation_model="gpt-4o-mini"),
            ["text", "Hello"],
            None,
            {1: "x", "generation_model": "gpt-4o-mini"},
        ]
        bad_bindings = [
            binding_fields(authorized=True),
            {k: v for k, v in binding_fields().items() if k != "provider"},
            binding_fields(credential_source="CUSTOMER"),
            binding_fields(credential_source=CredentialSource.CUSTOMER),
            binding_fields(scope_id=f"scope {CANARY}"),
            "scope-A",
        ]
        rig = Rig()
        for request in bad_requests:
            with self.subTest(request=repr(request)[:60]):
                self.assertBoundary(await rig.handler.process("evidence-invoke", binding_fields(), request), ErrorCode.INVALID_INPUT)
        for binding in bad_bindings:
            with self.subTest(binding=repr(binding)[:60]):
                self.assertBoundary(await rig.handler.process("evidence-invoke", binding, text_request()), ErrorCode.INVALID_INPUT)
        for request in ({"operation": "generate_text"}, {"operation": "GENERATE_TEXT", "model": "gpt-4o-mini"},
                        {"operation": "generate_text", "model": "gpt-4o-mini", "text": "customer content"}):
            with self.subTest(validation=repr(request)[:60]):
                self.assertBoundary(await rig.handler.validate("evidence-validate", binding_fields(), request), ErrorCode.INVALID_INPUT)
        self.assertEqual(rig.verifier.calls, 0)
        self.assertEqual(rig.log.events, [])

    async def test_raw_text_limit_checked_before_strip(self):
        rig = Rig()
        padded = " " * LOCAL_LIMIT_PROFILE.max_text_bytes + "a"
        self.assertBoundary(await rig.handler.process("evidence-invoke", binding_fields(), text_request(padded)), ErrorCode.INVALID_INPUT)
        oversized_audio = audio_request(audio=b"\x01" * (LOCAL_LIMIT_PROFILE.max_audio_bytes + 1))
        self.assertBoundary(await rig.handler.process("evidence-invoke", binding_fields(), oversized_audio), ErrorCode.INVALID_INPUT)
        self.assertEqual(rig.verifier.calls, 0)


class ProjectionTests(HandlerTestCase):
    async def test_input_projection_matrix(self):
        """TC-10: L4 composition and the three legacy success fields."""
        cases = [
            ("text only", text_request("  Hello  "), None, FileType.TEXT, "Hello"),
            ("audio only", audio_request(), "hi there", FileType.AUDIO, AUDIO_INSTRUCTION + TRANSCRIPT_SEPARATOR + "hi there"),
            ("text and audio", audio_request(text=" Describe "), "hi there", FileType.AUDIO, "Describe" + TRANSCRIPT_SEPARATOR + "hi there"),
            ("whitespace text and audio", audio_request(text="   "), "hi there", FileType.AUDIO, AUDIO_INSTRUCTION + TRANSCRIPT_SEPARATOR + "hi there"),
            ("empty audio is text only (C3)", audio_request(text="Hello", audio=b""), None, FileType.TEXT, "Hello"),
            ("empty transcript", audio_request(), "", FileType.AUDIO, AUDIO_INSTRUCTION),
        ]
        for name, request, transcript, file_type, prompt in cases:
            with self.subTest(case=name):
                rig = Rig()
                if transcript is not None:
                    rig.h.adapter.scripts["transcribe_audio"].append(Script(output=transcript))
                result = await rig.handler.process("evidence-invoke", binding_fields(), request)
                self.assertIsInstance(result, InvocationResult)
                self.assertIs(result.outcome, Outcome.SUCCESS)
                self.assertIs(result.file_type, file_type)
                self.assertEqual(rig.h.adapter.calls_for("generate_text")[0].text, prompt)
                self.assertEqual(len(rig.h.adapter.calls_for("transcribe_audio")), 0 if transcript is None else 1)
                projected = legacy_success(result)
                self.assertEqual(set(projected.model_dump()), {"result", "model", "file_type"})
                self.assertEqual(projected.model_dump(),
                                 {"result": "Synthetic answer", "model": "gpt-4o-mini", "file_type": file_type.value})

    async def test_audio_requires_both_allowed_targets(self):
        rig = Rig(targets=frozenset({GENERATE_TARGET}))
        result = await rig.handler.process("evidence-invoke", binding_fields(), audio_request())
        self.assertBoundary(result, ErrorCode.ACCESS_DENIED)
        self.assertEqual(rig.h.store.admit_calls, 0)

    async def test_failures_cannot_be_projected(self):
        rig = Rig()
        rig.h.adapter.scripts["generate_text"].append(Script(output=""))
        failure = await rig.handler.process("evidence-invoke", binding_fields(), text_request())
        self.assertIs(failure.error_code, ErrorCode.PROVIDER_RESPONSE_INVALID)
        boundary = await rig.handler.process("evidence-unknown", binding_fields(), text_request())
        for value in (failure, boundary, None, {"result": "x", "model": "m", "file_type": "text"}):
            with self.subTest(value=type(value).__name__), self.assertRaises(TypeError):
                legacy_success(value)


class ValidationHandlerTests(HandlerTestCase):
    async def test_validation_handler(self):
        rig = Rig()
        await rig.h.store.add_pending("scope-A", "credential-A", "v2", key=KEY_SCOPE_A_V2, targets=BOTH_TARGETS)
        rig.verifier.register("evidence-v2", rig.h.context(kind=ContextKind.VALIDATE, credential_version="v2"))
        result = await rig.handler.validate("evidence-v2", binding_fields(credential_version="v2"),
                                            {"operation": "generate_text", "model": "gpt-4o-mini"})
        self.assertIsInstance(result, ValidationResult)
        self.assertIs(result.status, ValidationStatus.VALID)
        self.assertEqual(result.binding.credential_version, "v2")
        self.assertEqual(rig.h.store.active_version("scope-A", "credential-A"), "v1")
        denied = await rig.handler.validate("evidence-invoke", binding_fields(),
                                            {"operation": "generate_text", "model": "gpt-4o-mini"})
        self.assertBoundary(denied, ErrorCode.ACCESS_DENIED)
        self.assertEqual(rig.log.events, ["verify", "admit", "verify"])


class UnconfiguredAndOutageTests(HandlerTestCase):
    async def test_unconfigured_and_reader_outage(self):
        """TC-13: the default wiring denies everything; outages fail closed."""
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": ENV_KEY_CANARY}):
            handler = build_unconfigured()
            for call in (
                handler.process("any-evidence", binding_fields(), text_request()),
                handler.validate("any-evidence", binding_fields(), {"operation": "generate_text", "model": "gpt-4o-mini"}),
            ):
                result = await call
                self.assertBoundary(result, ErrorCode.ACCESS_DENIED)
                self.assertNotIn(ENV_KEY_CANARY, repr(result))
            rig = Rig()
            rig.h.store.outage = True
            outage = await rig.handler.process("evidence-invoke", binding_fields(), text_request())
            self.assertIs(outage.error_code, ErrorCode.CREDENTIAL_UNAVAILABLE)
            self.assertEqual(rig.h.adapter.sessions_opened, 0)
            validation = await rig.handler.validate("evidence-validate", binding_fields(),
                                                    {"operation": "generate_text", "model": "gpt-4o-mini"})
            self.assertEqual((validation.status, validation.reason_code),
                             (ValidationStatus.INDETERMINATE, ErrorCode.CREDENTIAL_UNAVAILABLE))

    def test_build_handler_composes_real_adapter_without_test_seam(self):
        handler = build_handler(verifier=FakeContextVerifier(Harness().clock), reader=Harness().store,
                                providers={"openai": make_provider_config()})
        adapter = handler._orchestrator._adapters["openai"]
        self.assertIsInstance(adapter, OpenAIAdapter)
        self.assertIsNone(adapter._transport)  # A5: never set by wiring
        self.assertEqual(adapter._max_response_bytes, LOCAL_LIMIT_PROFILE.max_response_body_bytes)
        self.assertEqual(adapter._connect_timeout, float(LOCAL_LIMIT_PROFILE.connect_timeout_seconds))
        self.assertEqual(adapter.supported_operations(), BOTH_TARGETS)
        with self.assertRaises(ValueError):
            build_handler(verifier=FakeContextVerifier(Harness().clock), reader=Harness().store,
                          providers={"other-provider": make_provider_config("other-provider")})


class NoBypassTests(HandlerTestCase):
    async def test_no_bypass(self):
        """TC-14 (local): verifier always first; nothing selects fakes or public routes."""
        rig = Rig()
        await rig.handler.process("evidence-invoke", binding_fields(), text_request())
        await rig.handler.validate("evidence-validate", binding_fields(), {"operation": "generate_text", "model": "gpt-4o-mini"})
        self.assertEqual(rig.log.events, ["verify", "admit", "verify", "admit"])

        for name in ("handler.py", "wiring.py"):
            source = (PACKAGE_DIR / name).read_text(encoding="utf-8")
            for token in ("os.environ", "getenv", "dotenv", "fakes", "tests.", "fastapi", "APIRouter", "transport="):
                with self.subTest(file=name, token=token):
                    self.assertNotIn(token, source)
        for path in [REPO_ROOT / "main.py", *sorted((REPO_ROOT / "api").glob("*.py"))]:
            with self.subTest(legacy=path.name):
                self.assertNotIn("provider_integration", path.read_text(encoding="utf-8"))

    def test_wiring_import_does_not_load_sdk(self):
        script = (
            "import sys\n"
            f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
            "import services.provider_integration.wiring\n"
            "print('loaded=' + ','.join(sorted(m for m in ('openai', 'httpx', 'fastapi', 'pydantic', 'dotenv') if m in sys.modules)))\n"
        )
        env = {name: os.environ[name] for name in ("SYSTEMROOT", "PATH", "TEMP", "TMP") if name in os.environ}
        completed = subprocess.run([sys.executable, "-I", "-c", script], env=env, cwd=str(REPO_ROOT),
                                   capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(completed.returncode, 0)
        self.assertIn("loaded=\n", completed.stdout)


class DeadlineTests(HandlerTestCase):
    async def test_deadline_includes_verification(self):
        started = []

        class SpyOrchestrator(Orchestrator):
            async def invoke(self, context, request, *, started_at=None):
                started.append(started_at)
                return await super().invoke(context, request, started_at=started_at)

        seen = {}

        class SlowVerifier(FakeContextVerifier):
            def __init__(self, clock, gate):
                super().__init__(clock)
                self.gate = gate

            async def verify(self, *args):
                seen["verify_at"] = asyncio.get_running_loop().time()
                await self.gate.pause()
                return await super().verify(*args)

        h = Harness(limits=FAST_LIMITS)
        orchestrator = SpyOrchestrator(config=h.config, reader=h.store, adapters={"openai": h.adapter}, utc_now=h.clock.now)
        gate = PauseGate()
        verifier = SlowVerifier(h.clock, gate)
        verifier.register("evidence", h.context())
        handler = Handler(verifier=verifier, orchestrator=orchestrator, limits=FAST_LIMITS)

        task = asyncio.create_task(handler.process("evidence", binding_fields(), text_request()))
        await gate.entered.wait()
        gate.release.set()
        result = await task
        self.assertIs(result.outcome, Outcome.SUCCESS)
        self.assertEqual(len(started), 1)
        self.assertLessEqual(started[0], seen["verify_at"])  # budget starts at handler entry

        slow = SlowVerifier(h.clock, PauseGate())  # never released
        slow.register("evidence", h.context())
        denied = await Handler(verifier=slow, orchestrator=orchestrator, limits=FAST_LIMITS).process(
            "evidence", binding_fields(), text_request())
        self.assertBoundary(denied, ErrorCode.ACCESS_DENIED)  # gate never released again: verify timeout


class EndToEndTests(HandlerTestCase):
    async def test_end_to_end_with_real_adapter(self):
        """First combined run: core + real OpenAI adapter over a mocked transport."""
        recorder = Recorder(
            chat_response("Synthetic answer"),
            transcription_response(text="hi there"),
            chat_response("Audio answer"),
            error_response(401, "invalid_api_key"),
            chat_response(content="OK"),
        )
        h = Harness()
        adapter = OpenAIAdapter(BOTH_TARGETS, connect_timeout_seconds=5,
                                max_response_bytes=LOCAL_LIMIT_PROFILE.max_response_body_bytes,
                                transport=recorder.transport())
        orchestrator = Orchestrator(config=h.config, reader=h.store, adapters={"openai": adapter}, utc_now=h.clock.now)
        verifier = FakeContextVerifier(h.clock)
        verifier.register("evidence-invoke", h.context())
        verifier.register("evidence-validate", h.context(kind=ContextKind.VALIDATE))
        handler = Handler(verifier=verifier, orchestrator=orchestrator, limits=LOCAL_LIMIT_PROFILE)

        text = await handler.process("evidence-invoke", binding_fields(), text_request("Hello"))
        self.assertEqual(legacy_success(text).model_dump(), {"result": "Synthetic answer", "model": "gpt-4o-mini", "file_type": "text"})
        self.assertEqual(text.usage[0].input_tokens, 10)

        audio = await handler.process("evidence-invoke", binding_fields(), audio_request())
        self.assertEqual(legacy_success(audio).model_dump(), {"result": "Audio answer", "model": "gpt-4o-mini", "file_type": "audio"})
        self.assertEqual([u.operation.value for u in audio.usage], ["transcribe_audio", "generate_text"])

        rejected = await handler.process("evidence-invoke", binding_fields(), text_request("Hello"))
        self.assertIs(rejected.error_code, ErrorCode.CREDENTIAL_REJECTED)
        self.assertIsNone(rejected.result)

        validation = await handler.validate("evidence-validate", binding_fields(), {"operation": "generate_text", "model": "gpt-4o-mini"})
        self.assertIs(validation.status, ValidationStatus.VALID)

        self.assertEqual(len(recorder.requests), 5)
        self.assertEqual({r.url.host for r in recorder.requests}, {"provider.example.test"})
        self.assertEqual({r.headers["authorization"] for r in recorder.requests}, {"Bearer test-provider-key-scope-a-v1"})
        self.assertEqual((h.store.in_flight, orchestrator.capacity_in_use), (0, 0))


if __name__ == "__main__":
    unittest.main()
