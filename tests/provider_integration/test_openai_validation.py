"""T3.2 adapter validation tests (TC-04 adapter half, per C2): probes and outcome mapping.

Core validation orchestration lives in test_validation.py. Offline, synthetic only.
"""

import json
import unittest

import httpx

from services.provider_integration import (
    Binding,
    CredentialLease,
    CredentialSource,
    CredentialState,
    ErrorCode,
    Operation,
    ProbeOutcome,
    ProviderIntegrationError,
    SecretValue,
    UsageEntry,
    ValidationStatus,
)
from services.provider_integration.adapters import openai as adapter_module
from services.provider_integration.adapters.openai import build_silent_wav

from fakes import BOTH_TARGETS, GENERATE_TARGET, KEY_SCOPE_A, TRANSCRIBE_TARGET, make_provider_config, network_guard_patchers
from test_openai_adapter import BODY_CANARY, Recorder, chat_response, error_response, make_adapter, make_lease, transcription_response

_patches = []
VALID, REJECTED, INDETERMINATE = ValidationStatus.VALID, ValidationStatus.REJECTED, ValidationStatus.INDETERMINATE


def setUpModule():
    for patcher in network_guard_patchers():
        patcher.start()
        _patches.append(patcher)


def tearDownModule():
    while _patches:
        _patches.pop().stop()


async def probe(recorder, target, lease=None, max_response_bytes=1_048_576, remaining=5.0):
    adapter = make_adapter(recorder, max_response_bytes=max_response_bytes)
    async with adapter.open_session(lease or make_lease(), make_provider_config()) as session:
        return await session.validate_access(target, remaining)


def outcome_cases():
    """L6 status table (with A2), shared by the text and audio probes."""
    cases = [
        ("401 invalid key", lambda: error_response(401, "invalid_api_key", "invalid_request_error"), REJECTED, ErrorCode.CREDENTIAL_REJECTED),
        ("401 other", lambda: error_response(401, "ip_not_authorized"), INDETERMINATE, ErrorCode.ACCESS_DENIED),
        ("403 region (A2)", lambda: error_response(403, "unsupported_country_region_territory"), INDETERMINATE, ErrorCode.ACCESS_DENIED),
        ("404 model", lambda: error_response(404, "model_not_found"), REJECTED, ErrorCode.CAPABILITY_DENIED),
        ("404 other", lambda: error_response(404), INDETERMINATE, ErrorCode.PROVIDER_RESPONSE_INVALID),
        ("429 legacy quota type", lambda: error_response(429, None, "insufficient_quota"), INDETERMINATE, ErrorCode.QUOTA_EXCEEDED),
        ("429 other", lambda: error_response(429, "rate_limit_exceeded"), INDETERMINATE, ErrorCode.RATE_LIMITED),
        ("timeout", lambda: httpx.ReadTimeout("synthetic"), INDETERMINATE, ErrorCode.PROVIDER_TIMEOUT),
        ("connection", lambda: httpx.ConnectError("synthetic"), INDETERMINATE, ErrorCode.PROVIDER_UNAVAILABLE),
        ("408", lambda: error_response(408), INDETERMINATE, ErrorCode.PROVIDER_UNAVAILABLE),
        ("500", lambda: error_response(500), INDETERMINATE, ErrorCode.PROVIDER_UNAVAILABLE),
        ("503", lambda: error_response(503, "server_is_overloaded"), INDETERMINATE, ErrorCode.PROVIDER_UNAVAILABLE),
        ("400", lambda: error_response(400), INDETERMINATE, ErrorCode.INVALID_INPUT),
        ("413", lambda: error_response(413), INDETERMINATE, ErrorCode.INVALID_INPUT),
        ("422", lambda: error_response(422), INDETERMINATE, ErrorCode.INVALID_INPUT),
        ("418", lambda: error_response(418), INDETERMINATE, ErrorCode.PROVIDER_RESPONSE_INVALID),
        ("redirect", lambda: httpx.Response(302, headers={"location": "https://attacker.example.test/"}), INDETERMINATE, ErrorCode.PROVIDER_RESPONSE_INVALID),
        ("malformed", lambda: httpx.Response(200, content=b"not-json"), INDETERMINATE, ErrorCode.PROVIDER_RESPONSE_INVALID),
    ]
    for code in sorted(adapter_module.QUOTA_CODES):
        cases.append((f"429 {code}", lambda c=code: error_response(429, c, "insufficient_quota"), INDETERMINATE, ErrorCode.QUOTA_EXCEEDED))
    return cases


class ProbeRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_probe_request(self):
        recorder = Recorder(chat_response(content="OK", request_id="req_probe_1"))
        outcome = await probe(recorder, GENERATE_TARGET)
        self.assertIsInstance(outcome, ProbeOutcome)
        self.assertEqual((outcome.status, outcome.reason_code), (VALID, None))
        self.assertEqual(outcome.usage, UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini", input_tokens=10, output_tokens=5,
                                                   total_tokens=15, provider_request_id="req_probe_1"))
        self.assertEqual(len(recorder.requests), 1)
        body = json.loads(recorder.requests[0].content)
        self.assertEqual(body["messages"], [{"role": "user", "content": "Reply with OK."}])  # B5: no system prompt
        self.assertEqual((body["max_tokens"], body["temperature"], body["store"]), (8, 0, False))
        self.assertEqual(body["model"], "gpt-4o-mini")

    async def test_audio_probe_request(self):
        wav = build_silent_wav()
        self.assertEqual(len(wav), 44 + 32_000)  # 1 s, 16 kHz, mono, 16-bit PCM
        self.assertTrue(wav.startswith(b"RIFF") and wav[8:12] == b"WAVE")
        self.assertEqual(set(wav[44:]), {0})
        recorder = Recorder(transcription_response(text=""))
        outcome = await probe(recorder, TRANSCRIBE_TARGET)
        self.assertEqual((outcome.status, outcome.reason_code), (VALID, None))  # empty transcript is valid
        self.assertEqual(len(recorder.requests), 1)
        content = recorder.requests[0].content
        self.assertIn(b'filename="input.wav"', content)
        self.assertIn(wav, content)
        self.assertIn(b"gpt-4o-mini-transcribe", content)
        self.assertEqual(str(recorder.requests[0].url).rsplit("/", 2)[-2:], ["audio", "transcriptions"])

    async def test_probe_success_criteria(self):
        cases = [
            ("empty text", GENERATE_TARGET, chat_response(content=""), INDETERMINATE),
            ("whitespace text", GENERATE_TARGET, chat_response(content="   "), INDETERMINATE),
            ("no content", GENERATE_TARGET, chat_response(content=None), INDETERMINATE),
            ("no choices", GENERATE_TARGET, httpx.Response(200, json={"id": "x", "object": "chat.completion", "choices": []}), INDETERMINATE),
            ("any wording", GENERATE_TARGET, chat_response(content="Sure!"), VALID),
            ("transcript missing", TRANSCRIBE_TARGET, httpx.Response(200, json={"usage": {"type": "duration", "seconds": 1}}), INDETERMINATE),
            ("transcript text", TRANSCRIBE_TARGET, transcription_response(text="..."), VALID),
        ]
        for name, target, response, status in cases:
            with self.subTest(case=name):
                outcome = await probe(Recorder(response), target)
                self.assertIs(outcome.status, status)
                if status is INDETERMINATE:
                    self.assertIs(outcome.reason_code, ErrorCode.PROVIDER_RESPONSE_INVALID)


class OutcomeMatrixTests(unittest.IsolatedAsyncioTestCase):
    async def test_probe_and_outcome_matrix(self):
        """TC-04 (adapter): definitive rejections only; inconclusive results never claim an invalid key."""
        for target in (GENERATE_TARGET, TRANSCRIBE_TARGET):
            for name, make_response, status, reason in outcome_cases():
                with self.subTest(target=target.operation.value, case=name):
                    recorder = Recorder(make_response())
                    outcome = await probe(recorder, target)
                    self.assertIs(outcome.status, status)
                    self.assertIs(outcome.reason_code, reason)
                    self.assertEqual(len(recorder.requests), 1)  # one probe, no retry
                    self.assertEqual((outcome.usage.operation, outcome.usage.model), (target.operation, target.model))
                    rendered = repr(outcome)
                    self.assertNotIn(KEY_SCOPE_A, rendered)
                    self.assertNotIn(BODY_CANARY, rendered)

    async def test_oversized_probe_response_is_indeterminate(self):
        outcome = await probe(Recorder(httpx.Response(200, content=b"x" * 8192)), GENERATE_TARGET, max_response_bytes=4096)
        self.assertEqual((outcome.status, outcome.reason_code), (INDETERMINATE, ErrorCode.PROVIDER_RESPONSE_INVALID))


class LifecycleAndScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_pending_lease_and_no_activation(self):
        pending = CredentialLease(
            binding=Binding("scope-A", "credential-A", "v2", CredentialSource.CUSTOMER, "openai"),
            state=CredentialState.PENDING,
            secret=SecretValue("test-provider-key-scope-a-v2"),
            permitted_targets=BOTH_TARGETS,
            admission_id="admission-2",
        )
        recorder = Recorder(chat_response(content="OK"))
        outcome = await probe(recorder, GENERATE_TARGET, lease=pending)
        self.assertIs(outcome.status, VALID)
        self.assertEqual(recorder.requests[0].headers["authorization"], "Bearer test-provider-key-scope-a-v2")
        adapter = make_adapter(recorder)
        for name in ("activate", "rotate", "disable", "delete", "set_active"):
            with self.subTest(attribute=name):
                self.assertFalse(hasattr(adapter, name))

    async def test_probe_rejects_bad_targets_and_time_before_sending(self):
        recorder = Recorder()
        narrow = make_lease(targets=frozenset({GENERATE_TARGET}))
        for lease, target, remaining, code in (
            (narrow, TRANSCRIBE_TARGET, 5.0, ErrorCode.UNSUPPORTED_OPERATION),
            (make_lease(), GENERATE_TARGET, 0, ErrorCode.OPERATION_TIMEOUT),
            (make_lease(), GENERATE_TARGET, float("nan"), ErrorCode.OPERATION_TIMEOUT),
        ):
            with self.subTest(code=code.value, remaining=repr(remaining)), self.assertRaises(ProviderIntegrationError) as caught:
                await probe(recorder, target, lease=lease, remaining=remaining)
            self.assertIs(caught.exception.code, code)
        self.assertEqual(recorder.requests, [])


if __name__ == "__main__":
    unittest.main()
