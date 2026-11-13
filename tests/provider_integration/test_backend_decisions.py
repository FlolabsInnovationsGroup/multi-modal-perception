"""Lead decisions on the backend answers (2026-11-13): T4.4 (D-5) and T4.5 (D-1).

D-5: the backend chooses the model per request; the service runs it only if it
is also an approved target here, and never substitutes another model.
D-1: both customer-managed and platform-managed keys are in scope; the source
named in the trusted binding must match the stored record, and a failure with
one source never falls back to the other.

Runs through the internal Handler with the fake verifier/store and the scripted
adapter only. No network, environment keys or real credentials.
"""

import unittest

from services.provider_integration import (
    ContextKind,
    CredentialSource,
    ErrorCode,
    InvocationResult,
    Operation,
    Outcome,
    Target,
    ValidationResult,
    ValidationStatus,
)
from services.provider_integration.config import ModuleConfig
from services.provider_integration.errors import ProviderOperationError
from services.provider_integration.handler import Handler
from services.provider_integration.orchestrator import Orchestrator

from fakes import (
    BOTH_TARGETS,
    GENERATE_TARGET,
    KEY_SCOPE_A,
    TRANSCRIBE_TARGET,
    FakeContextVerifier,
    Harness,
    ScriptedAdapter,
    Script,
    make_provider_config,
    network_guard_patchers,
)
from test_handler import Rig, audio_request, binding_fields, text_request

UNAPPROVED_GENERATION = Target(Operation.GENERATE_TEXT, "gpt-unapproved-model")
UNAPPROVED_TRANSCRIPTION = Target(Operation.TRANSCRIBE_AUDIO, "gpt-unapproved-transcribe")
REPLACEMENT_GENERATION = Target(Operation.GENERATE_TEXT, "gpt-replacement-model")
PLATFORM_KEY = "test-provider-key-platform-v1"
_patches = []


def setUpModule():
    for patcher in network_guard_patchers():
        patcher.start()
        _patches.append(patcher)


def tearDownModule():
    while _patches:
        _patches.pop().stop()


class ModelChoiceTests(unittest.IsolatedAsyncioTestCase):
    """T4.4 / D-5: backend-chosen models are double-checked against approved targets."""

    def assertRefusedBeforeKey(self, rig, result, code):
        self.assertIsInstance(result, InvocationResult)
        self.assertIs(result.outcome, Outcome.ERROR)
        self.assertIs(result.error_code, code)
        self.assertIsNone(result.result)
        self.assertEqual(rig.h.store.admit_calls, 0, "the key must not be read for a refused model")
        self.assertEqual(rig.h.adapter.calls, [], "no provider call, so no substitute model either")

    async def test_unapproved_generation_model_is_refused_even_when_backend_allows_it(self):
        rig = Rig(targets=BOTH_TARGETS | {UNAPPROVED_GENERATION})
        result = await rig.handler.process(
            "evidence-invoke", binding_fields(), dict(text_request(), generation_model=UNAPPROVED_GENERATION.model)
        )
        self.assertRefusedBeforeKey(rig, result, ErrorCode.UNSUPPORTED_OPERATION)

    async def test_unapproved_transcription_model_is_refused_even_when_backend_allows_it(self):
        rig = Rig(targets=BOTH_TARGETS | {UNAPPROVED_TRANSCRIPTION})
        request = dict(audio_request(), transcription_model=UNAPPROVED_TRANSCRIPTION.model)
        result = await rig.handler.process("evidence-invoke", binding_fields(), request)
        self.assertRefusedBeforeKey(rig, result, ErrorCode.UNSUPPORTED_OPERATION)

    async def test_unapproved_model_validation_is_indeterminate_without_a_probe(self):
        rig = Rig(targets=BOTH_TARGETS | {UNAPPROVED_GENERATION})
        result = await rig.handler.validate(
            "evidence-validate", binding_fields(),
            {"operation": "generate_text", "model": UNAPPROVED_GENERATION.model},
        )
        self.assertIsInstance(result, ValidationResult)
        self.assertIs(result.status, ValidationStatus.INDETERMINATE)
        self.assertIs(result.reason_code, ErrorCode.UNSUPPORTED_OPERATION)
        self.assertEqual((rig.h.store.admit_calls, rig.h.adapter.calls), (0, []))

    async def test_approved_model_outside_the_backend_choice_is_denied(self):
        """An approved model the backend did not authorize for this request is never used."""
        rig = Rig(targets=frozenset({GENERATE_TARGET}))
        result = await rig.handler.process("evidence-invoke", binding_fields(), audio_request())
        self.assertIs(result.error_code, ErrorCode.ACCESS_DENIED)
        self.assertEqual((rig.h.store.admit_calls, rig.h.adapter.calls), (0, []))

    async def test_backend_chosen_approved_model_runs_exactly(self):
        rig = Rig()
        result = await rig.handler.process("evidence-invoke", binding_fields(), audio_request())
        self.assertIs(result.outcome, Outcome.SUCCESS)
        self.assertEqual([call.target for call in rig.h.adapter.calls], [TRANSCRIBE_TARGET, GENERATE_TARGET])
        self.assertEqual(result.model, GENERATE_TARGET.model)

    async def test_replacement_model_runs_once_approved_on_both_sides(self):
        """Adding a replacement model is a configuration change here plus the backend's choice."""
        approved = BOTH_TARGETS | {REPLACEMENT_GENERATION}
        h = Harness()
        h.store.add_record("scope-R", "credential-R", "v1", key="test-provider-key-scope-r-v1",
                           targets=approved, active=True)
        adapter = ScriptedAdapter(approved)
        orchestrator = Orchestrator(
            config=ModuleConfig(limits=h.config.limits, providers={"openai": make_provider_config(targets=approved)}),
            reader=h.store, adapters={"openai": adapter}, utc_now=h.clock.now,
        )
        verifier = FakeContextVerifier(h.clock)
        verifier.register("evidence-r", h.context(scope_id="scope-R", credential_ref="credential-R",
                                                  targets=frozenset({REPLACEMENT_GENERATION})))
        handler = Handler(verifier=verifier, orchestrator=orchestrator, limits=h.config.limits)
        result = await handler.process(
            "evidence-r", binding_fields(scope_id="scope-R", credential_ref="credential-R"),
            dict(text_request(), generation_model=REPLACEMENT_GENERATION.model),
        )
        self.assertIs(result.outcome, Outcome.SUCCESS)
        self.assertEqual(result.model, REPLACEMENT_GENERATION.model)
        self.assertEqual([call.target for call in adapter.calls], [REPLACEMENT_GENERATION])


class KeySourceTests(unittest.IsolatedAsyncioTestCase):
    """T4.5 / D-1: customer and platform keys both work and never substitute for each other."""

    def platform_rig(self):
        rig = Rig()
        rig.h.store.add_record("scope-A", "credential-P", "v1", key=PLATFORM_KEY,
                               source=CredentialSource.PLATFORM, targets=BOTH_TARGETS, active=True)
        rig.verifier.register("evidence-platform", rig.h.context(
            credential_ref="credential-P", credential_source=CredentialSource.PLATFORM))
        return rig

    @staticmethod
    def platform_binding():
        return binding_fields(credential_ref="credential-P", credential_source="platform")

    async def test_customer_key_runs_with_the_customer_key(self):
        rig = Rig()
        result = await rig.handler.process("evidence-invoke", binding_fields(), text_request())
        self.assertIs(result.outcome, Outcome.SUCCESS)
        self.assertEqual([call.key for call in rig.h.adapter.calls], [KEY_SCOPE_A])

    async def test_platform_key_runs_with_the_platform_key(self):
        rig = self.platform_rig()
        result = await rig.handler.process("evidence-platform", self.platform_binding(), audio_request())
        self.assertIs(result.outcome, Outcome.SUCCESS)
        self.assertEqual([call.key for call in rig.h.adapter.calls], [PLATFORM_KEY, PLATFORM_KEY])

    async def test_platform_key_validation_is_bound_to_the_platform_source(self):
        rig = self.platform_rig()
        rig.verifier.register("evidence-platform-validate", rig.h.context(
            kind=ContextKind.VALIDATE, credential_ref="credential-P",
            credential_source=CredentialSource.PLATFORM))
        result = await rig.handler.validate("evidence-platform-validate", self.platform_binding(),
                                            {"operation": "generate_text", "model": "gpt-4o-mini"})
        self.assertIs(result.status, ValidationStatus.VALID)
        self.assertIs(result.binding.credential_source, CredentialSource.PLATFORM)
        self.assertEqual([call.key for call in rig.h.adapter.calls], [PLATFORM_KEY])

    async def test_source_mismatch_with_the_stored_record_is_denied_both_ways(self):
        cases = (
            ("customer record, platform claimed", "credential-A", CredentialSource.PLATFORM, "platform"),
            ("platform record, customer claimed", "credential-P", CredentialSource.CUSTOMER, "customer"),
        )
        for name, ref, source, source_text in cases:
            with self.subTest(case=name):
                rig = self.platform_rig()
                rig.verifier.register("evidence-mismatch", rig.h.context(credential_ref=ref, credential_source=source))
                result = await rig.handler.process(
                    "evidence-mismatch", binding_fields(credential_ref=ref, credential_source=source_text), text_request()
                )
                self.assertIs(result.outcome, Outcome.ERROR)
                self.assertIs(result.error_code, ErrorCode.ACCESS_DENIED)
                self.assertEqual(rig.h.adapter.calls, [])

    async def test_rejected_customer_key_never_falls_back_to_the_platform_key(self):
        rig = self.platform_rig()
        rig.h.adapter.scripts["generate_text"].append(Script(error=ProviderOperationError(ErrorCode.CREDENTIAL_REJECTED)))
        result = await rig.handler.process("evidence-invoke", binding_fields(), text_request())
        self.assertIs(result.error_code, ErrorCode.CREDENTIAL_REJECTED)
        self.assertEqual([call.key for call in rig.h.adapter.calls], [KEY_SCOPE_A])
        self.assertEqual(rig.h.store.admit_calls, 1)

    async def test_unavailable_customer_key_never_falls_back_to_the_platform_key(self):
        rig = self.platform_rig()
        await rig.h.store.disable("scope-A", "credential-A", "v1")
        result = await rig.handler.process("evidence-invoke", binding_fields(), text_request())
        self.assertIs(result.error_code, ErrorCode.CREDENTIAL_UNAVAILABLE)
        self.assertEqual(rig.h.adapter.calls, [])
        self.assertEqual(rig.h.store.admit_calls, 1)


if __name__ == "__main__":
    unittest.main()
