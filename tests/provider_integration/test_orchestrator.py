"""T2.3 orchestrator tests: ordering, composition, no fallback, safe failures, cleanup.

Uses the scripted adapter double only; the real OpenAI adapter is T3.
"""

import asyncio
import unittest

from services.provider_integration import (
    AudioFormat,
    ContextKind,
    CredentialState,
    ErrorCode,
    FileType,
    Operation,
    Outcome,
    ProviderIntegrationError,
    ProviderOperationError,
    Target,
    UsageEntry,
)
from services.provider_integration.orchestrator import AUDIO_INSTRUCTION, TRANSCRIPT_SEPARATOR

from fakes import (
    BOTH_TARGETS,
    FAST_LIMITS,
    GENERATE_TARGET,
    KEY_SCOPE_A,
    KEY_SCOPE_B,
    SYNTHETIC_DESTINATION,
    TRANSCRIBE_TARGET,
    Harness,
    PauseGate,
    RaisingReader,
    Script,
    TamperingReader,
    network_guard_patchers,
)

CONTENT_CANARY = "content-canary-do-not-echo"
_patches = []


def setUpModule():
    for patcher in network_guard_patchers():
        patcher.start()
        _patches.append(patcher)


def tearDownModule():
    while _patches:
        _patches.pop().stop()


class OrchestratorTestCase(unittest.IsolatedAsyncioTestCase):
    def assertCleanExit(self, harness):
        self.assertEqual(harness.store.in_flight, 0)
        self.assertEqual(harness.orchestrator.capacity_in_use, 0)
        self.assertEqual(harness.adapter.sessions_opened, harness.adapter.sessions_closed)

    def assertNoLeak(self, result, *secrets):
        rendered = repr(result) + str(result.error_code) + str(result.usage)
        for secret in secrets + (KEY_SCOPE_A, KEY_SCOPE_B):
            self.assertNotIn(secret, rendered)


class SuccessAndCompositionTests(OrchestratorTestCase):
    async def test_text_only_success(self):
        h = Harness()
        context = h.context()
        result = await h.orchestrator.invoke(context, h.text_request("  Hello  "))
        self.assertIs(result.outcome, Outcome.SUCCESS)
        self.assertEqual(result.result, "Synthetic answer")
        self.assertEqual((result.provider, result.model, result.file_type), ("openai", "gpt-4o-mini", FileType.TEXT))
        self.assertEqual(result.request_id, context.request_id)
        self.assertEqual(result.usage, (UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini"),))
        generation = h.adapter.calls_for("generate_text")
        self.assertEqual(len(generation), 1)
        self.assertEqual(generation[0].text, "Hello")
        self.assertEqual(generation[0].key, KEY_SCOPE_A)
        self.assertEqual(h.adapter.calls_for("transcribe_audio"), [])
        self.assertEqual(h.adapter.opened_with[0][1], SYNTHETIC_DESTINATION)
        self.assertEqual((h.adapter.sessions_opened, h.store.admissions_total), (1, 1))
        self.assertCleanExit(h)

    async def test_input_composition_matrix(self):
        """TC-10 (core): L4 composition matches the existing /process behaviour."""
        cases = [
            ("audio only", "", "  hi there  ", AUDIO_INSTRUCTION + TRANSCRIPT_SEPARATOR + "hi there"),
            ("text and audio", "  Describe  ", "hi there", "Describe" + TRANSCRIPT_SEPARATOR + "hi there"),
            ("audio only, empty transcript", "", "   ", AUDIO_INSTRUCTION),
            ("text, empty transcript", "Describe", "", "Describe"),
        ]
        for name, text, transcript, expected_prompt in cases:
            with self.subTest(case=name):
                h = Harness()
                h.adapter.scripts["transcribe_audio"].append(Script(output=transcript))
                request = h.audio_request(text=text, audio=b"\x01\x02\x03", audio_format=AudioFormat.MP3)
                result = await h.orchestrator.invoke(h.context(), request)
                self.assertIs(result.outcome, Outcome.SUCCESS)
                self.assertIs(result.file_type, FileType.AUDIO)
                self.assertEqual([c.operation for c in h.adapter.calls], ["transcribe_audio", "generate_text"])
                transcription, generation = h.adapter.calls
                self.assertEqual((transcription.audio_length, transcription.audio_format), (3, AudioFormat.MP3))
                self.assertEqual(generation.text, expected_prompt)
                self.assertEqual([u.operation for u in result.usage], [Operation.TRANSCRIBE_AUDIO, Operation.GENERATE_TEXT])
                self.assertCleanExit(h)

    async def test_one_session_and_admission_per_request(self):
        h = Harness()
        for _ in range(2):
            self.assertIs((await h.orchestrator.invoke(h.context(), h.text_request())).outcome, Outcome.SUCCESS)
        admissions = [opened[0] for opened in h.adapter.opened_with]
        self.assertEqual(len(set(admissions)), 2)
        self.assertEqual(len(h.adapter.calls_for("generate_text")), 2)  # no response cache

    async def test_two_scopes_same_prompt_isolated(self):
        """TC-03 (core): overlapping requests use their own key, session and answer."""
        h = Harness()
        h.adapter.generation_by_key = {KEY_SCOPE_A: "answer for A", KEY_SCOPE_B: "answer for B"}
        barrier = asyncio.Barrier(2)
        h.adapter.scripts["generate_text"].extend([Script(barrier=barrier), Script(barrier=barrier)])
        context_a = h.context()
        context_b = h.context(scope_id="scope-B", credential_ref="credential-B")
        result_a, result_b = await asyncio.gather(
            h.orchestrator.invoke(context_a, h.text_request("Same prompt")),
            h.orchestrator.invoke(context_b, h.text_request("Same prompt")),
        )
        self.assertEqual((result_a.result, result_b.result), ("answer for A", "answer for B"))
        self.assertEqual({(c.scope_id, c.key) for c in h.adapter.calls},
                         {("scope-A", KEY_SCOPE_A), ("scope-B", KEY_SCOPE_B)})
        self.assertEqual(h.adapter.sessions_opened, 2)
        again = await h.orchestrator.invoke(h.context(), h.text_request("Same prompt"))
        self.assertEqual(again.result, "answer for A")
        self.assertEqual(len(h.adapter.calls_for("generate_text")), 3)
        self.assertCleanExit(h)


def failure_classes():
    """(name, script factory(target), expected code, usage expectation: 'reported'|'null'|None)."""
    def operation_error(code, with_usage=True):
        def make(target):
            usage = UsageEntry(target.operation, target.model, input_tokens=3) if with_usage else None
            return Script(error=ProviderOperationError(code, usage))
        return make

    classes = [
        (f"operation error {code.value}", operation_error(code), code, "reported")
        for code in (
            ErrorCode.CREDENTIAL_REJECTED, ErrorCode.ACCESS_DENIED, ErrorCode.CAPABILITY_DENIED,
            ErrorCode.RATE_LIMITED, ErrorCode.QUOTA_EXCEEDED, ErrorCode.PROVIDER_UNAVAILABLE,
            ErrorCode.PROVIDER_TIMEOUT, ErrorCode.INVALID_INPUT, ErrorCode.PROVIDER_RESPONSE_INVALID,
        )
    ]
    classes += [
        ("operation error without usage", operation_error(ErrorCode.RATE_LIMITED, with_usage=False), ErrorCode.RATE_LIMITED, "null"),
        ("not attempted", lambda t: Script(error=ProviderIntegrationError(ErrorCode.UNSUPPORTED_OPERATION)), ErrorCode.UNSUPPORTED_OPERATION, None),
        ("unexpected exception", lambda t: Script(error=RuntimeError(f"sdk boom {KEY_SCOPE_A} {CONTENT_CANARY}")), ErrorCode.INTERNAL_ERROR, "null"),
        ("malformed return", lambda t: Script(raw={"text": CONTENT_CANARY}), ErrorCode.PROVIDER_RESPONSE_INVALID, "null"),
        ("step timeout", lambda t: Script(hang=True), ErrorCode.PROVIDER_TIMEOUT, "null"),
    ]
    return classes


class NoFallbackTests(OrchestratorTestCase):
    async def test_no_fallback_matrix(self):
        """TC-07: every failure is explicit, single-attempt, same provider, no echo."""
        for stage, target in (("transcribe_audio", TRANSCRIBE_TARGET), ("generate_text", GENERATE_TARGET)):
            for name, make_script, code, usage_kind in failure_classes():
                with self.subTest(stage=stage, failure=name):
                    h = Harness(limits=FAST_LIMITS)
                    h.adapter.scripts[stage].append(make_script(target))
                    result = await h.orchestrator.invoke(h.context(), h.audio_request(text=CONTENT_CANARY))
                    self.assertIs(result.outcome, Outcome.ERROR)
                    self.assertIs(result.error_code, code)
                    self.assertIsNone(result.result)
                    self.assertEqual(len(h.adapter.calls_for(stage)), 1)
                    if stage == "transcribe_audio":
                        self.assertEqual(h.adapter.calls_for("generate_text"), [])
                    self.assertEqual((h.other_adapter.calls, h.other_adapter.sessions_opened), ([], 0))
                    self.assertEqual(h.store.admissions_total, 1)
                    self.assertNoLeak(result, CONTENT_CANARY)

                    prior = [UsageEntry(Operation.TRANSCRIBE_AUDIO, "gpt-4o-mini-transcribe")] if stage == "generate_text" else []
                    if usage_kind is None:
                        expected = prior
                    elif usage_kind == "null":
                        expected = prior + [UsageEntry(target.operation, target.model)]
                    else:
                        expected = prior + [UsageEntry(target.operation, target.model, input_tokens=3)]
                    self.assertEqual(list(result.usage), expected)
                    self.assertCleanExit(h)

    async def test_empty_or_oversized_generation_is_invalid(self):
        for output in ("", "   \n"):
            with self.subTest(output=repr(output)):
                h = Harness()
                h.adapter.scripts["generate_text"].append(Script(output=output))
                result = await h.orchestrator.invoke(h.context(), h.text_request(CONTENT_CANARY))
                self.assertIs(result.error_code, ErrorCode.PROVIDER_RESPONSE_INVALID)
                self.assertEqual(len(result.usage), 1)
                self.assertNoLeak(result, CONTENT_CANARY)

    async def test_generation_containing_key_fails_safely(self):
        h = Harness()
        h.adapter.scripts["generate_text"].append(Script(output=f"the key is {KEY_SCOPE_A}"))
        result = await h.orchestrator.invoke(h.context(), h.text_request())
        self.assertIs(result.error_code, ErrorCode.INTERNAL_ERROR)
        self.assertIsNone(result.result)
        self.assertNoLeak(result)

    async def test_usage_survives_generation_failure(self):
        """TC-11 (core): completed transcription usage is retained; nothing is summed."""
        h = Harness()
        h.adapter.scripts["transcribe_audio"].append(
            Script(output="hello", usage=UsageEntry(Operation.TRANSCRIBE_AUDIO, "gpt-4o-mini-transcribe", audio_seconds=1.5))
        )
        h.adapter.scripts["generate_text"].append(Script(error=ProviderOperationError(ErrorCode.PROVIDER_UNAVAILABLE)))
        result = await h.orchestrator.invoke(h.context(), h.audio_request())
        self.assertIs(result.error_code, ErrorCode.PROVIDER_UNAVAILABLE)
        self.assertEqual(result.usage[0].audio_seconds, 1.5)
        self.assertEqual(result.usage[1], UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini"))
        self.assertIsNone(result.usage[1].total_tokens)

    async def test_usage_is_sanitized(self):
        h = Harness()
        h.adapter.scripts["transcribe_audio"].append(
            Script(output="hi", usage=UsageEntry(Operation.GENERATE_TEXT, "some-other-model", input_tokens=99))
        )
        h.adapter.scripts["generate_text"].append(
            Script(output="ok", usage=UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini", output_tokens=2,
                                                 provider_request_id=f"req-{KEY_SCOPE_A}"))
        )
        result = await h.orchestrator.invoke(h.context(), h.audio_request())
        self.assertEqual(result.usage[0], UsageEntry(Operation.TRANSCRIBE_AUDIO, "gpt-4o-mini-transcribe"))
        self.assertEqual(result.usage[1].output_tokens, 2)
        self.assertIsNone(result.usage[1].provider_request_id)
        self.assertNoLeak(result)


class DenialTests(OrchestratorTestCase):
    async def test_tampered_lease_never_reaches_provider(self):
        """TC-02 (core): the orchestrator re-checks the reader's snapshot."""
        h0 = Harness()
        cases = [
            ("other version", dict(binding=h0.context(credential_version="v2").binding), ErrorCode.ACCESS_DENIED),
            ("other scope", dict(binding=h0.context(scope_id="scope-B", credential_ref="credential-B").binding), ErrorCode.ACCESS_DENIED),
            ("pending state", dict(state=CredentialState.PENDING), ErrorCode.CREDENTIAL_UNAVAILABLE),
            ("narrower targets", dict(targets=frozenset({GENERATE_TARGET})), ErrorCode.CAPABILITY_DENIED),
            ("not a lease", dict(replacement="not a lease"), ErrorCode.ACCESS_DENIED),
        ]
        for name, overrides, code in cases:
            with self.subTest(case=name):
                h = Harness(reader_factory=lambda store, o=overrides: TamperingReader(store, **o))
                result = await h.orchestrator.invoke(h.context(), h.audio_request())
                self.assertIs(result.error_code, code)
                self.assertEqual((h.adapter.sessions_opened, h.adapter.calls), (0, []))
                self.assertCleanExit(h)

    async def test_denied_before_reader(self):
        """TC-01/TC-02 (core): local denials make zero reader and provider calls."""
        other_model = Target(Operation.GENERATE_TEXT, "gpt-4o")
        h0 = Harness()
        cases = [
            ("validation context", lambda h: h.context(kind=ContextKind.VALIDATE), h0.text_request(), ErrorCode.ACCESS_DENIED),
            ("expired context", lambda h: h.context(lifetime=0), h0.text_request(), ErrorCode.ACCESS_DENIED),
            ("target outside context", lambda h: h.context(targets=frozenset({GENERATE_TARGET})), h0.audio_request(), ErrorCode.ACCESS_DENIED),
            ("unsupported model", lambda h: h.context(targets=frozenset({other_model})), h0.text_request(generation=other_model), ErrorCode.UNSUPPORTED_OPERATION),
            ("unconfigured provider", lambda h: h.context(provider="unconfigured"), h0.text_request(), ErrorCode.NOT_CONFIGURED),
        ]
        for name, make_context, request, code in cases:
            with self.subTest(case=name):
                h = Harness()
                result = await h.orchestrator.invoke(make_context(h), request)
                self.assertIs(result.error_code, code)
                self.assertEqual((h.store.admit_calls, h.adapter.sessions_opened), (0, 0))
                self.assertCleanExit(h)
        with self.subTest(case="adapter supports less than config"):
            h = Harness(adapter_targets=frozenset({GENERATE_TARGET}))
            result = await h.orchestrator.invoke(h.context(), h.audio_request())
            self.assertIs(result.error_code, ErrorCode.UNSUPPORTED_OPERATION)
            self.assertEqual(h.store.admit_calls, 0)

    async def test_reader_failures_pass_through_safely(self):
        h = Harness()
        await h.store.disable("scope-A", "credential-A", "v1")
        result = await h.orchestrator.invoke(h.context(), h.text_request())
        self.assertIs(result.error_code, ErrorCode.CREDENTIAL_UNAVAILABLE)
        self.assertEqual(h.adapter.sessions_opened, 0)

        canary = f"backend detail {KEY_SCOPE_A}"
        h = Harness(reader_factory=lambda store: RaisingReader(canary))
        result = await h.orchestrator.invoke(h.context(), h.text_request())
        self.assertIs(result.error_code, ErrorCode.CREDENTIAL_UNAVAILABLE)
        self.assertNoLeak(result, canary)
        self.assertEqual(h.orchestrator.capacity_in_use, 0)

    async def test_session_open_failures(self):
        for error, code in (
            (RuntimeError(f"open failed {KEY_SCOPE_A}"), ErrorCode.INTERNAL_ERROR),
            (ProviderIntegrationError(ErrorCode.PROVIDER_UNAVAILABLE), ErrorCode.PROVIDER_UNAVAILABLE),
        ):
            with self.subTest(code=code.value):
                h = Harness()
                h.adapter.open_error = error
                result = await h.orchestrator.invoke(h.context(), h.text_request())
                self.assertIs(result.error_code, code)
                self.assertEqual((h.adapter.calls, result.usage), ([], ()))
                self.assertNoLeak(result)
                self.assertCleanExit(h)


class CleanupTests(OrchestratorTestCase):
    async def test_cleanup_failure_keeps_result(self):
        """D3: a session close error does not change the outcome and is not retained."""
        h = Harness()
        h.adapter.close_error = RuntimeError(f"close failed {KEY_SCOPE_A}")
        result = await h.orchestrator.invoke(h.context(), h.text_request())
        self.assertIs(result.outcome, Outcome.SUCCESS)
        self.assertNoLeak(result)
        self.assertCleanExit(h)

    async def test_cancellation_propagates_after_cleanup(self):
        h = Harness()
        gate = PauseGate()
        h.adapter.scripts["generate_text"].append(Script(gate=gate))
        task = asyncio.create_task(h.orchestrator.invoke(h.context(), h.text_request()))
        await gate.entered.wait()
        self.assertEqual((h.store.in_flight, h.orchestrator.capacity_in_use), (1, 1))
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(h.adapter.sessions_closed, 1)
        self.assertCleanExit(h)


if __name__ == "__main__":
    unittest.main()
