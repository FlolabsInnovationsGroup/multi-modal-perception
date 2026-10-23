"""T2.3 core validation tests (TC-04 core half, C2; TC-05 core).

Adapter probes and provider outcome mapping are T3.2 in test_openai_validation.py.
"""

import asyncio
import dataclasses
import inspect
import unittest

from services.provider_integration import (
    LOCAL_LIMIT_PROFILE,
    ContextKind,
    ErrorCode,
    Operation,
    ProbeOutcome,
    ProviderIntegrationError,
    ProviderOperationError,
    ProviderSession,
    Target,
    UsageEntry,
    ValidationStatus,
)

from fakes import (
    BOTH_TARGETS,
    FAST_LIMITS,
    GENERATE_TARGET,
    KEY_SCOPE_A,
    KEY_SCOPE_A_V2,
    TRANSCRIBE_TARGET,
    Harness,
    PauseGate,
    Script,
    TamperingReader,
    network_guard_patchers,
    wait_for_calls,
)

_patches = []


def setUpModule():
    for patcher in network_guard_patchers():
        patcher.start()
        _patches.append(patcher)


def tearDownModule():
    while _patches:
        _patches.pop().stop()


def validate_context(h, **overrides):
    return h.context(kind=ContextKind.VALIDATE, **overrides)


class ValidationTestCase(unittest.IsolatedAsyncioTestCase):
    def assertProbeFree(self, h):
        self.assertEqual(h.adapter.calls_for("generate_text"), [])
        self.assertEqual(h.adapter.calls_for("transcribe_audio"), [])

    def assertCleanExit(self, h):
        self.assertEqual(h.store.in_flight, 0)
        self.assertEqual(h.orchestrator.capacity_in_use, 0)
        self.assertEqual(h.adapter.sessions_opened, h.adapter.sessions_closed)


class ProbeTests(ValidationTestCase):
    async def test_single_probe_valid_result(self):
        for target in (GENERATE_TARGET, TRANSCRIBE_TARGET):
            with self.subTest(target=target.operation.value):
                h = Harness()
                context = validate_context(h)
                result = await h.orchestrator.validate(context, h.validation_request(target))
                self.assertIs(result.status, ValidationStatus.VALID)
                self.assertIsNone(result.reason_code)
                self.assertEqual((result.request_id, result.binding, result.target), (context.request_id, context.binding, target))
                self.assertEqual(result.checked_at, h.clock.now())
                self.assertEqual(result.usage, (UsageEntry(target.operation, target.model),))
                probes = h.adapter.calls_for("validate_access")
                self.assertEqual(len(probes), 1)
                self.assertEqual((probes[0].target, probes[0].text, probes[0].audio_length), (target, None, None))
                self.assertEqual(probes[0].key, KEY_SCOPE_A)
                self.assertProbeFree(h)
                self.assertCleanExit(h)

    async def test_pending_version_validates_as_itself(self):
        """TC-05 (core): pending v2 is checked as v2, never activated, never invocable."""
        h = Harness()
        await h.store.add_pending("scope-A", "credential-A", "v2", key=KEY_SCOPE_A_V2, targets=BOTH_TARGETS)
        result = await h.orchestrator.validate(validate_context(h, credential_version="v2"), h.validation_request())
        self.assertIs(result.status, ValidationStatus.VALID)
        self.assertEqual(result.binding.credential_version, "v2")
        self.assertEqual(h.adapter.calls_for("validate_access")[0].key, KEY_SCOPE_A_V2)
        self.assertEqual(h.store.active_version("scope-A", "credential-A"), "v1")
        self.assertTrue(h.store.backend_accepts(result))

        pending_invoke = await h.orchestrator.invoke(h.context(credential_version="v2"), h.text_request())
        self.assertIs(pending_invoke.error_code, ErrorCode.CREDENTIAL_UNAVAILABLE)
        active_invoke = await h.orchestrator.invoke(h.context(), h.text_request())
        self.assertEqual(active_invoke.result, "Synthetic answer")
        self.assertEqual(h.adapter.calls_for("generate_text")[0].key, KEY_SCOPE_A)

    async def test_probe_outcome_matrix(self):
        """TC-04 (core): definitive rejections only; everything inconclusive is indeterminate."""
        usage = UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini", output_tokens=1)
        null = (UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini"),)
        cases = [
            ("probe rejected", Script(probe=ProbeOutcome(ValidationStatus.REJECTED, ErrorCode.CREDENTIAL_REJECTED, usage)),
             ValidationStatus.REJECTED, ErrorCode.CREDENTIAL_REJECTED, (usage,)),
            ("probe indeterminate", Script(probe=ProbeOutcome(ValidationStatus.INDETERMINATE, ErrorCode.RATE_LIMITED, usage)),
             ValidationStatus.INDETERMINATE, ErrorCode.RATE_LIMITED, (usage,)),
            ("not attempted rejection", Script(error=ProviderIntegrationError(ErrorCode.CREDENTIAL_REJECTED)),
             ValidationStatus.REJECTED, ErrorCode.CREDENTIAL_REJECTED, ()),
            ("unexpected exception", Script(error=RuntimeError(f"probe boom {KEY_SCOPE_A}")),
             ValidationStatus.INDETERMINATE, ErrorCode.INTERNAL_ERROR, null),
            ("malformed probe", Script(raw="valid"),
             ValidationStatus.INDETERMINATE, ErrorCode.PROVIDER_RESPONSE_INVALID, null),
        ]
        for code in (ErrorCode.CREDENTIAL_REJECTED, ErrorCode.CAPABILITY_DENIED):
            cases.append((f"raised {code.value}", Script(error=ProviderOperationError(code, usage)),
                          ValidationStatus.REJECTED, code, (usage,)))
        for code in (ErrorCode.QUOTA_EXCEEDED, ErrorCode.RATE_LIMITED, ErrorCode.PROVIDER_UNAVAILABLE,
                     ErrorCode.PROVIDER_TIMEOUT, ErrorCode.INVALID_INPUT, ErrorCode.ACCESS_DENIED,
                     ErrorCode.PROVIDER_RESPONSE_INVALID):
            cases.append((f"raised {code.value}", Script(error=ProviderOperationError(code)),
                          ValidationStatus.INDETERMINATE, code, null))
        for name, script, status, reason, expected_usage in cases:
            with self.subTest(case=name):
                h = Harness()
                h.adapter.scripts["validate_access"].append(script)
                result = await h.orchestrator.validate(validate_context(h), h.validation_request())
                self.assertIs(result.status, status)
                self.assertIs(result.reason_code, reason)
                self.assertEqual(result.usage, expected_usage)
                self.assertEqual(len(h.adapter.calls_for("validate_access")), 1)  # never retried
                self.assertNotIn(KEY_SCOPE_A, repr(result))
                self.assertEqual(h.store.active_version("scope-A", "credential-A"), "v1")
                self.assertCleanExit(h)


class LocalFailureTests(ValidationTestCase):
    async def test_local_failures_are_indeterminate(self):
        other_model = Target(Operation.GENERATE_TEXT, "gpt-4o")
        cases = [
            ("invoke context", lambda h: h.context(), GENERATE_TARGET, ErrorCode.ACCESS_DENIED, 0),
            ("expired context", lambda h: validate_context(h, lifetime=0), GENERATE_TARGET, ErrorCode.ACCESS_DENIED, 0),
            ("target outside context", lambda h: validate_context(h, targets=frozenset({GENERATE_TARGET})), TRANSCRIBE_TARGET, ErrorCode.ACCESS_DENIED, 0),
            ("unsupported model", lambda h: validate_context(h, targets=frozenset({other_model})), other_model, ErrorCode.UNSUPPORTED_OPERATION, 0),
            ("unconfigured provider", lambda h: validate_context(h, provider="unconfigured"), GENERATE_TARGET, ErrorCode.NOT_CONFIGURED, 0),
        ]
        for name, make_context, target, reason, admit_calls in cases:
            with self.subTest(case=name):
                h = Harness()
                result = await h.orchestrator.validate(make_context(h), h.validation_request(target))
                self.assertIs(result.status, ValidationStatus.INDETERMINATE)
                self.assertIs(result.reason_code, reason)
                self.assertEqual((h.store.admit_calls, h.adapter.sessions_opened, result.usage), (admit_calls, 0, ()))

    async def test_reader_and_lease_failures_are_indeterminate(self):
        h = Harness()
        h.store.outage = True
        result = await h.orchestrator.validate(validate_context(h), h.validation_request())
        self.assertEqual((result.status, result.reason_code), (ValidationStatus.INDETERMINATE, ErrorCode.CREDENTIAL_UNAVAILABLE))

        h = Harness()
        await h.store.disable("scope-A", "credential-A", "v1")
        result = await h.orchestrator.validate(validate_context(h), h.validation_request())
        self.assertEqual((result.status, result.reason_code), (ValidationStatus.INDETERMINATE, ErrorCode.CREDENTIAL_UNAVAILABLE))

        h = Harness()
        h.store.add_record("scope-A", "credential-G", "v1", key=KEY_SCOPE_A, targets=frozenset({GENERATE_TARGET}), active=True)
        result = await h.orchestrator.validate(
            validate_context(h, credential_ref="credential-G"), h.validation_request(TRANSCRIBE_TARGET)
        )
        # A local capability denial is not a provider rejection (D4).
        self.assertEqual((result.status, result.reason_code), (ValidationStatus.INDETERMINATE, ErrorCode.ACCESS_DENIED))

        h = Harness(reader_factory=lambda store: TamperingReader(store, binding=Harness().context(credential_version="v9").binding))
        result = await h.orchestrator.validate(validate_context(h), h.validation_request())
        self.assertEqual((result.status, result.reason_code), (ValidationStatus.INDETERMINATE, ErrorCode.ACCESS_DENIED))
        self.assertEqual(h.adapter.sessions_opened, 0)


class ValidationLimitTests(ValidationTestCase):
    async def test_probe_and_overall_timeouts(self):
        loop = asyncio.get_running_loop()
        h = Harness(limits=FAST_LIMITS)
        h.adapter.scripts["validate_access"].append(Script(hang=True))
        result = await h.orchestrator.validate(validate_context(h), h.validation_request())
        self.assertEqual((result.status, result.reason_code), (ValidationStatus.INDETERMINATE, ErrorCode.PROVIDER_TIMEOUT))
        self.assertEqual(result.usage, (UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini"),))
        self.assertCleanExit(h)

        h = Harness(limits=FAST_LIMITS)
        h.adapter.scripts["validate_access"].append(Script(hang=True))
        started = loop.time() - FAST_LIMITS.validation_timeout_seconds + 0.03
        result = await h.orchestrator.validate(validate_context(h), h.validation_request(), started_at=started)
        self.assertEqual(result.reason_code, ErrorCode.OPERATION_TIMEOUT)

        h = Harness(limits=FAST_LIMITS)
        result = await h.orchestrator.validate(validate_context(h), h.validation_request(), started_at=loop.time() - 10)
        self.assertEqual((result.reason_code, h.store.admit_calls), (ErrorCode.OPERATION_TIMEOUT, 0))

        h = Harness(limits=FAST_LIMITS)
        h.store.admit_gate = PauseGate()
        result = await h.orchestrator.validate(validate_context(h), h.validation_request())
        self.assertEqual(result.reason_code, ErrorCode.CREDENTIAL_UNAVAILABLE)
        self.assertEqual(h.adapter.sessions_opened, 0)

    async def test_capacity(self):
        h = Harness(limits=dataclasses.replace(LOCAL_LIMIT_PROFILE, max_concurrent_operations=1))
        gate = PauseGate()
        h.adapter.scripts["validate_access"].append(Script(gate=gate))
        first = asyncio.create_task(h.orchestrator.validate(validate_context(h), h.validation_request()))
        await wait_for_calls(h.adapter, 1, "validate_access")
        second = await h.orchestrator.validate(validate_context(h), h.validation_request())
        self.assertEqual((second.status, second.reason_code), (ValidationStatus.INDETERMINATE, ErrorCode.CAPACITY_EXCEEDED))
        self.assertEqual(h.store.admit_calls, 1)
        gate.release.set()
        self.assertIs((await first).status, ValidationStatus.VALID)
        self.assertCleanExit(h)


class ContentAndActivationTests(ValidationTestCase):
    async def test_no_customer_content_and_no_activation(self):
        self.assertEqual(list(inspect.signature(ProviderSession.validate_access).parameters),
                         ["self", "target", "remaining_seconds"])
        h = Harness()
        await h.orchestrator.validate(validate_context(h), h.validation_request())
        for name in ("activate", "rotate", "disable", "delete", "set_active", "add_pending"):
            with self.subTest(attribute=name):
                self.assertFalse(hasattr(h.orchestrator, name))
        self.assertEqual(h.store.active_version("scope-A", "credential-A"), "v1")


if __name__ == "__main__":
    unittest.main()
