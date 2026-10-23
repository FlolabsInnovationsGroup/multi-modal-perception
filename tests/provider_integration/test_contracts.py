"""T2.1 contract tests: types, errors, configuration, ports and import safety.

Offline only: real socket connections are denied for the whole module and all
credentials are synthetic ``test-provider-key-...`` placeholders.
"""

import copy
import dataclasses
import inspect
import json
import os
import pathlib
import pickle
import socket
import subprocess
import sys
import traceback
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from services.provider_integration import (
    LOCAL_LIMIT_PROFILE,
    SAFE_MESSAGES,
    AudioFormat,
    Binding,
    BoundaryFailure,
    ContextKind,
    ContextVerifier,
    CredentialLease,
    CredentialReader,
    CredentialSource,
    CredentialState,
    ErrorCode,
    FileType,
    GenerationSettings,
    InvocationInput,
    InvocationRequest,
    InvocationResult,
    LimitProfile,
    ModuleConfig,
    Operation,
    Outcome,
    ProbeOutcome,
    ProviderAdapter,
    ProviderConfig,
    ProviderIntegrationError,
    ProviderOperationError,
    ProviderSession,
    SecretValue,
    StepOutput,
    Target,
    UsageEntry,
    ValidationRequest,
    ValidationResult,
    ValidationStatus,
    VerifiedContext,
    is_valid_identifier,
    new_request_id,
    safe_message,
    sanitize_provider_request_id,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE_DIR = REPO_ROOT / "services" / "provider_integration"

KEY_CANARY = "test-provider-key-canary-0001"
CONTENT_CANARY = "content-canary-do-not-log"
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)

GEN = Target(Operation.GENERATE_TEXT, "gpt-4o-mini")
TRANSCRIBE = Target(Operation.TRANSCRIBE_AUDIO, "gpt-4o-mini-transcribe")

_patches = []


def setUpModule():
    def deny(*args, **kwargs):
        raise AssertionError("network access is not allowed in provider-integration tests")

    for target, attribute in ((socket.socket, "connect"), (socket.socket, "connect_ex"), (socket, "create_connection")):
        patcher = mock.patch.object(target, attribute, side_effect=deny)
        patcher.start()
        _patches.append(patcher)


def tearDownModule():
    while _patches:
        _patches.pop().stop()


def make_binding(**overrides):
    values = dict(
        scope_id="scope-A",
        credential_ref="credential-A",
        credential_version="v1",
        credential_source=CredentialSource.CUSTOMER,
        provider="openai",
    )
    values.update(overrides)
    return Binding(**values)


def make_context(**overrides):
    values = dict(
        binding=make_binding(),
        request_id=new_request_id(),
        kind=ContextKind.INVOKE,
        allowed_targets=frozenset({GEN}),
        expires_at=NOW + timedelta(minutes=5),
    )
    values.update(overrides)
    return VerifiedContext(**values)


def make_lease(secret=None, **overrides):
    values = dict(
        binding=make_binding(),
        state=CredentialState.ACTIVE,
        secret=secret or SecretValue(KEY_CANARY),
        permitted_targets=frozenset({GEN}),
        admission_id="admission-1",
    )
    values.update(overrides)
    return CredentialLease(**values)


def make_generation_settings(**overrides):
    values = dict(max_tokens=256, temperature=0.4, system_prompt="Synthetic system prompt.")
    values.update(overrides)
    return GenerationSettings(**values)


def make_provider_config(**overrides):
    values = dict(
        provider="openai",
        destination="https://provider.example.test/v1/",
        targets=frozenset({GEN, TRANSCRIBE}),
        generation=make_generation_settings(),
    )
    values.update(overrides)
    return ProviderConfig(**values)


def limit_values(**overrides):
    values = {f.name: getattr(LOCAL_LIMIT_PROFILE, f.name) for f in dataclasses.fields(LimitProfile)}
    values.update(overrides)
    return values


class IdentifierTests(unittest.TestCase):
    def test_accepts_allowed_characters_up_to_128(self):
        for value in ("scope-A", "a", "v1.2:rc_3", "x" * 128):
            with self.subTest(length=len(value)):
                self.assertTrue(is_valid_identifier(value))

    def test_rejects_invalid_identifiers(self):
        cases = ["", "x" * 129, "scope A", "scope/A", "scöpe", "scope-A\n", "١", None, 12, b"scope"]
        for value in cases:
            with self.subTest(case=repr(value)[:20]):
                self.assertFalse(is_valid_identifier(value))

    def test_identifier_error_does_not_reflect_value(self):
        with self.assertRaises(ValueError) as caught:
            make_binding(scope_id="untrusted value " + CONTENT_CANARY)
        self.assertNotIn(CONTENT_CANARY, str(caught.exception))


class EnumAndErrorCodeTests(unittest.TestCase):
    def test_enum_values_match_l2(self):
        self.assertEqual({m.value for m in Operation}, {"generate_text", "transcribe_audio"})
        self.assertEqual({m.value for m in CredentialSource}, {"customer", "platform"})
        self.assertEqual({m.value for m in ContextKind}, {"invoke", "validate"})
        self.assertEqual(
            {m.value for m in CredentialState}, {"active", "pending", "disabled", "deleted", "expired"}
        )
        self.assertEqual({m.value for m in Outcome}, {"success", "error"})
        self.assertEqual({m.value for m in ValidationStatus}, {"valid", "rejected", "indeterminate"})
        self.assertEqual({m.value for m in FileType}, {"text", "audio"})
        self.assertEqual(
            {m.value for m in AudioFormat}, {"wav", "mp3", "m4a", "webm", "mp4", "mpeg", "mpga"}
        )

    def test_error_codes_are_the_allowlist(self):
        expected = {
            "INVALID_INPUT", "ACCESS_DENIED", "NOT_CONFIGURED", "CREDENTIAL_UNAVAILABLE",
            "CREDENTIAL_REJECTED", "CAPABILITY_DENIED", "UNSUPPORTED_OPERATION", "RATE_LIMITED",
            "QUOTA_EXCEEDED", "PROVIDER_TIMEOUT", "PROVIDER_UNAVAILABLE", "INTERNAL_ERROR",
            "PROVIDER_RESPONSE_INVALID", "OPERATION_TIMEOUT", "CAPACITY_EXCEEDED",
        }
        self.assertEqual({code.value for code in ErrorCode}, expected)

    def test_every_code_has_a_fixed_message(self):
        self.assertEqual(set(SAFE_MESSAGES), set(ErrorCode))
        for code, message in SAFE_MESSAGES.items():
            with self.subTest(code=code.value):
                self.assertTrue(message)
                self.assertNotIn("{", message)
                self.assertNotIn("%", message)
                self.assertEqual(safe_message(code), message)
        with self.assertRaises(TypeError):
            SAFE_MESSAGES[ErrorCode.INTERNAL_ERROR] = "changed"  # type: ignore[index]

    def test_safe_message_requires_enum(self):
        with self.assertRaises(TypeError):
            safe_message("INTERNAL_ERROR")  # type: ignore[arg-type]


class BindingTests(unittest.TestCase):
    def test_valid_binding(self):
        binding = make_binding()
        self.assertEqual(binding.credential_version, "v1")

    def test_each_identifier_field_is_validated(self):
        for name in ("scope_id", "credential_ref", "credential_version", "provider"):
            with self.subTest(field=name), self.assertRaises(ValueError):
                make_binding(**{name: "not valid"})

    def test_source_must_be_enum_not_raw_string(self):
        with self.assertRaises(TypeError):
            make_binding(credential_source="customer")

    def test_exact_equality_without_case_folding(self):
        base = make_binding()
        changes = {
            "scope_id": "scope-B",
            "credential_ref": "credential-B",
            "credential_version": "v2",
            "credential_source": CredentialSource.PLATFORM,
            "provider": "other-provider",
        }
        for name, value in changes.items():
            with self.subTest(field=name):
                self.assertNotEqual(base, make_binding(**{name: value}))
        self.assertNotEqual(base, make_binding(scope_id="SCOPE-A"))
        self.assertEqual(base, make_binding())

    def test_binding_is_immutable(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            make_binding().scope_id = "scope-B"  # type: ignore[misc]

    def test_unknown_fields_rejected(self):
        with self.assertRaises(TypeError):
            Binding(  # type: ignore[call-arg]
                scope_id="scope-A",
                credential_ref="credential-A",
                credential_version="v1",
                credential_source=CredentialSource.CUSTOMER,
                provider="openai",
                authorized=True,
            )


class TargetAndContextTests(unittest.TestCase):
    def test_target_requires_operation_enum_and_identifier_model(self):
        with self.assertRaises(TypeError):
            Target("generate_text", "gpt-4o-mini")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            Target(Operation.GENERATE_TEXT, "bad model")

    def test_context_permits_exact_targets_only(self):
        context = make_context()
        self.assertTrue(context.permits(GEN))
        self.assertFalse(context.permits(Target(Operation.GENERATE_TEXT, "GPT-4O-MINI")))
        self.assertFalse(context.permits(Target(Operation.GENERATE_TEXT, "gpt-4o")))
        self.assertFalse(context.permits(Target(Operation.TRANSCRIBE_AUDIO, "gpt-4o-mini")))
        self.assertFalse(context.permits(("generate_text", "gpt-4o-mini")))  # type: ignore[arg-type]

    def test_context_requires_nonempty_frozenset_of_targets(self):
        for value in (frozenset(), {GEN}, [GEN], frozenset({("generate_text", "gpt-4o-mini")})):
            with self.subTest(value=type(value).__name__), self.assertRaises(TypeError):
                make_context(allowed_targets=value)

    def test_context_expiry_must_be_utc(self):
        with self.assertRaises(ValueError):
            make_context(expires_at=datetime(2026, 10, 23, 12, 5))
        with self.assertRaises(ValueError):
            make_context(expires_at=datetime(2026, 10, 23, 12, 5, tzinfo=timezone(timedelta(hours=3))))

    def test_context_expiry_boundary(self):
        context = make_context(expires_at=NOW)
        self.assertTrue(context.is_expired(NOW))
        self.assertTrue(context.is_expired(NOW + timedelta(microseconds=1)))
        self.assertFalse(context.is_expired(NOW - timedelta(microseconds=1)))
        with self.assertRaises(ValueError):
            context.is_expired(datetime(2026, 10, 23, 12, 0))

    def test_context_kind_must_be_enum(self):
        with self.assertRaises(TypeError):
            make_context(kind="invoke")


class CapabilityMatrixTests(unittest.TestCase):
    def test_capability_matrix(self):
        """TC-01 (core): only configured operation/model pairs are supported."""
        config = ModuleConfig(limits=LOCAL_LIMIT_PROFILE, providers={"openai": make_provider_config()})
        supported = [GEN, TRANSCRIBE]
        unsupported = [
            Target(Operation.GENERATE_TEXT, "gpt-4o"),
            Target(Operation.TRANSCRIBE_AUDIO, "gpt-4o-mini"),
            Target(Operation.GENERATE_TEXT, "GPT-4O-MINI"),
        ]
        for target in supported:
            with self.subTest(target=target):
                self.assertTrue(config.supports("openai", target))
        for target in unsupported:
            with self.subTest(target=target):
                self.assertFalse(config.supports("openai", target))
        self.assertFalse(config.supports("OpenAI", GEN))
        self.assertFalse(config.supports("anthropic", GEN))
        self.assertIsNone(config.provider_config("anthropic"))

    def test_empty_configuration_enables_nothing(self):
        config = ModuleConfig(limits=LOCAL_LIMIT_PROFILE, providers={})
        self.assertFalse(config.supports("openai", GEN))


class InvocationTypeTests(unittest.TestCase):
    def test_text_only_request(self):
        request = InvocationRequest(content=InvocationInput(text="Hello"), generation_target=GEN)
        self.assertEqual(request.targets, frozenset({GEN}))
        self.assertFalse(request.content.has_audio)

    def test_text_only_forbids_unused_transcription_target(self):
        with self.assertRaises(ValueError):
            InvocationRequest(
                content=InvocationInput(text="Hello"), generation_target=GEN, transcription_target=TRANSCRIBE
            )

    def test_audio_requires_format_and_both_targets(self):
        with self.assertRaises(TypeError):
            InvocationInput(text="", audio=b"\x00\x01")
        audio_input = InvocationInput(text="", audio=b"\x00\x01", audio_format=AudioFormat.WAV)
        with self.assertRaises(TypeError):
            InvocationRequest(content=audio_input, generation_target=GEN)
        request = InvocationRequest(content=audio_input, generation_target=GEN, transcription_target=TRANSCRIBE)
        self.assertEqual(request.targets, frozenset({GEN, TRANSCRIBE}))

    def test_target_operations_must_match_roles(self):
        audio_input = InvocationInput(text="Hi", audio=b"\x00", audio_format=AudioFormat.MP3)
        with self.assertRaises(ValueError):
            InvocationRequest(content=audio_input, generation_target=TRANSCRIBE, transcription_target=TRANSCRIBE)
        with self.assertRaises(ValueError):
            InvocationRequest(content=audio_input, generation_target=GEN, transcription_target=GEN)

    def test_missing_content_rejected(self):
        for text in ("", "   \n\t"):
            with self.subTest(text=repr(text)), self.assertRaises(ValueError):
                InvocationInput(text=text)
        with self.assertRaises(ValueError):
            InvocationInput(text="", audio=b"")

    def test_format_without_audio_rejected(self):
        with self.assertRaises(ValueError):
            InvocationInput(text="Hello", audio=b"", audio_format=AudioFormat.WAV)

    def test_audio_must_be_immutable_bytes_and_format_enum(self):
        with self.assertRaises(TypeError):
            InvocationInput(text="Hi", audio=bytearray(b"\x00"), audio_format=AudioFormat.WAV)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            InvocationInput(text="Hi", audio=b"\x00", audio_format="wav")  # type: ignore[arg-type]

    def test_content_absent_from_repr(self):
        item = InvocationInput(text=CONTENT_CANARY, audio=CONTENT_CANARY.encode(), audio_format=AudioFormat.WAV)
        request = InvocationRequest(content=item, generation_target=GEN, transcription_target=TRANSCRIBE)
        self.assertNotIn(CONTENT_CANARY, repr(item))
        self.assertNotIn(CONTENT_CANARY, repr(request))

    def test_validation_request_has_one_target_and_no_content(self):
        request = ValidationRequest(target=GEN)
        self.assertEqual([f.name for f in dataclasses.fields(request)], ["target"])
        with self.assertRaises(TypeError):
            ValidationRequest(target="generate_text")  # type: ignore[arg-type]


class SecretValueTests(unittest.TestCase):
    def test_repr_str_and_format_are_redacted(self):
        secret = SecretValue(KEY_CANARY)
        for rendered in (repr(secret), str(secret), f"{secret}", f"{secret!r}", "%s" % secret, format(secret, "")):
            with self.subTest(rendered=rendered):
                self.assertNotIn(KEY_CANARY, rendered)
                self.assertIn("redacted", rendered)

    def test_serialization_and_copy_refused(self):
        secret = SecretValue(KEY_CANARY)
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
            with self.subTest(protocol=protocol), self.assertRaises(TypeError):
                pickle.dumps(secret, protocol=protocol)
        with self.assertRaises(TypeError):
            copy.copy(secret)
        with self.assertRaises(TypeError):
            copy.deepcopy(secret)
        with self.assertRaises(TypeError):
            json.dumps(secret)
        with self.assertRaises(TypeError):
            json.dumps({"key": secret}, default=lambda obj: obj.__getstate__())

    def test_no_instance_dict_and_immutable(self):
        secret = SecretValue(KEY_CANARY)
        with self.assertRaises(TypeError):
            vars(secret)
        with self.assertRaises(AttributeError):
            secret.value = "other"  # type: ignore[attr-defined]
        with self.assertRaises(AttributeError):
            del secret._SecretValue__value  # type: ignore[attr-defined]

    def test_identity_equality(self):
        first = SecretValue(KEY_CANARY)
        second = SecretValue(KEY_CANARY)
        self.assertEqual(first, first)
        self.assertNotEqual(first, second)
        self.assertNotEqual(first, KEY_CANARY)
        self.assertEqual(len({first, second}), 2)

    def test_reveal_and_appears_in(self):
        secret = SecretValue(KEY_CANARY)
        self.assertEqual(secret.reveal_for_session(), KEY_CANARY)
        self.assertTrue(secret.appears_in(f"prefix {KEY_CANARY} suffix"))
        self.assertFalse(secret.appears_in("test-provider-key-canary"))
        self.assertFalse(secret.appears_in(None))

    def test_invalid_values_rejected_without_reflection(self):
        for value in ("", " " + KEY_CANARY, KEY_CANARY + "\n", None, b"test-provider-key-bytes"):
            with self.subTest(case=type(value).__name__), self.assertRaises(ValueError) as caught:
                SecretValue(value)  # type: ignore[arg-type]
            self.assertNotIn(KEY_CANARY, str(caught.exception))


class CredentialLeaseTests(unittest.TestCase):
    def test_lease_repr_excludes_secret(self):
        lease = make_lease()
        self.assertNotIn(KEY_CANARY, repr(lease))
        self.assertIn("credential-A", repr(lease))

    def test_lease_serialization_and_copy_refused(self):
        lease = make_lease()
        with self.assertRaises(TypeError):
            pickle.dumps(lease)
        with self.assertRaises(TypeError):
            copy.copy(lease)
        with self.assertRaises(TypeError):
            copy.deepcopy(lease)
        with self.assertRaises(TypeError):
            dataclasses.asdict(lease)

    def test_lease_identity_equality(self):
        secret = SecretValue(KEY_CANARY)
        self.assertNotEqual(make_lease(secret=secret), make_lease(secret=secret))

    def test_lease_fields_validated(self):
        with self.assertRaises(TypeError):
            make_lease(state="active")
        with self.assertRaises(TypeError):
            make_lease(secret=KEY_CANARY)
        with self.assertRaises(TypeError):
            make_lease(permitted_targets=frozenset())
        with self.assertRaises(ValueError):
            make_lease(admission_id="not valid")


class UsageAndSafeIdTests(unittest.TestCase):
    def test_usage_and_safe_ids(self):
        """TC-11 (core): null is unavailable, zero stays zero, nothing is derived, IDs filtered."""
        absent = UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini")
        self.assertIsNone(absent.input_tokens)
        self.assertIsNone(absent.total_tokens)
        self.assertIsNone(absent.audio_seconds)

        zero = UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini", input_tokens=0, output_tokens=0, total_tokens=0)
        self.assertEqual((zero.input_tokens, zero.output_tokens, zero.total_tokens), (0, 0, 0))

        reported = UsageEntry.from_reported(Operation.GENERATE_TEXT, "gpt-4o-mini", input_tokens=10, output_tokens=5)
        self.assertIsNone(reported.total_tokens)

        malformed = UsageEntry.from_reported(
            Operation.TRANSCRIBE_AUDIO,
            "gpt-4o-mini-transcribe",
            input_tokens=-1,
            output_tokens="5",
            total_tokens=True,
            audio_seconds=float("nan"),
        )
        self.assertEqual(
            (malformed.input_tokens, malformed.output_tokens, malformed.total_tokens, malformed.audio_seconds),
            (None, None, None, None),
        )
        self.assertIsNone(UsageEntry.from_reported(Operation.TRANSCRIBE_AUDIO, "m", audio_seconds=float("inf")).audio_seconds)
        self.assertEqual(UsageEntry.from_reported(Operation.TRANSCRIBE_AUDIO, "m", audio_seconds=1).audio_seconds, 1.0)

        secret = SecretValue(KEY_CANARY)
        self.assertEqual(sanitize_provider_request_id("req_123", secret), "req_123")
        for bad in ("x" * 129, "req 123", "req\n123", "", None, 7, KEY_CANARY, f"req-{KEY_CANARY}"):
            with self.subTest(case=repr(bad)[:16]):
                self.assertIsNone(sanitize_provider_request_id(bad, secret))
        self.assertIsNone(
            UsageEntry.from_reported(Operation.GENERATE_TEXT, "m", provider_request_id=KEY_CANARY, secret=secret).provider_request_id
        )

    def test_constructor_rejects_negative_bool_and_malformed(self):
        for name, value in (("input_tokens", -1), ("output_tokens", True), ("total_tokens", 1.5)):
            with self.subTest(field=name), self.assertRaises(ValueError):
                UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini", **{name: value})
        for value in (-0.1, float("nan"), True, "1"):
            with self.subTest(audio=repr(value)), self.assertRaises(ValueError):
                UsageEntry(Operation.TRANSCRIBE_AUDIO, "gpt-4o-mini-transcribe", audio_seconds=value)
        with self.assertRaises(ValueError):
            UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini", provider_request_id="bad id")


class ResultInvariantTests(unittest.TestCase):
    def make_result(self, **overrides):
        values = dict(
            request_id=new_request_id(),
            provider="openai",
            model="gpt-4o-mini",
            file_type=FileType.TEXT,
            outcome=Outcome.SUCCESS,
            result="Synthetic answer",
        )
        values.update(overrides)
        return InvocationResult(**values)

    def test_success_requires_nonempty_result_and_no_error(self):
        self.assertEqual(self.make_result().result, "Synthetic answer")
        for bad in (None, "", "   "):
            with self.subTest(result=repr(bad)), self.assertRaises(ValueError):
                self.make_result(result=bad)
        with self.assertRaises(ValueError):
            self.make_result(error_code=ErrorCode.INTERNAL_ERROR)

    def test_error_requires_null_result_and_allowlisted_code(self):
        failure = self.make_result(outcome=Outcome.ERROR, result=None, error_code=ErrorCode.ACCESS_DENIED)
        self.assertIsNone(failure.result)
        with self.assertRaises(ValueError):
            self.make_result(outcome=Outcome.ERROR, error_code=ErrorCode.ACCESS_DENIED)
        with self.assertRaises(TypeError):
            self.make_result(outcome=Outcome.ERROR, result=None, error_code=None)
        with self.assertRaises(TypeError):
            self.make_result(outcome=Outcome.ERROR, result=None, error_code="ACCESS_DENIED")

    def test_usage_must_be_tuple_of_entries(self):
        entry = UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini")
        self.assertEqual(self.make_result(usage=(entry,)).usage, (entry,))
        with self.assertRaises(TypeError):
            self.make_result(usage=[entry])
        with self.assertRaises(TypeError):
            self.make_result(usage=({"input_tokens": 1},))

    def test_result_content_absent_from_repr(self):
        self.assertNotIn(CONTENT_CANARY, repr(self.make_result(result=CONTENT_CANARY)))

    def test_boundary_failure_reflects_nothing(self):
        failure = BoundaryFailure.create(ErrorCode.ACCESS_DENIED)
        self.assertEqual(failure.outcome, Outcome.ERROR)
        self.assertIsNone(failure.result)
        self.assertEqual(failure.usage, ())
        self.assertEqual(
            {f.name for f in dataclasses.fields(failure)}, {"request_id", "error_code", "outcome", "result", "usage"}
        )
        self.assertNotEqual(BoundaryFailure.create(ErrorCode.INVALID_INPUT).request_id, failure.request_id)

    def test_boundary_failure_codes_and_ids(self):
        for code in set(ErrorCode) - {ErrorCode.INVALID_INPUT, ErrorCode.ACCESS_DENIED}:
            with self.subTest(code=code.value), self.assertRaises(ValueError):
                BoundaryFailure.create(code)
        for request_id in ("caller-supplied-id", new_request_id().upper(), None):
            with self.subTest(request_id=repr(request_id)[:12]), self.assertRaises(ValueError):
                BoundaryFailure(request_id=request_id, error_code=ErrorCode.ACCESS_DENIED)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            BoundaryFailure(request_id=new_request_id(), error_code=ErrorCode.ACCESS_DENIED, result="x")  # type: ignore[call-arg]


class ValidationResultTests(unittest.TestCase):
    def make_validation(self, **overrides):
        values = dict(
            request_id=new_request_id(),
            binding=make_binding(credential_version="v2"),
            target=GEN,
            checked_at=NOW,
            status=ValidationStatus.VALID,
        )
        values.update(overrides)
        return ValidationResult(**values)

    def test_result_keeps_exact_checked_version(self):
        self.assertEqual(self.make_validation().binding.credential_version, "v2")

    def test_status_reason_rules(self):
        self.make_validation()
        with self.assertRaises(ValueError):
            self.make_validation(reason_code=ErrorCode.PROVIDER_TIMEOUT)
        for code in (ErrorCode.CREDENTIAL_REJECTED, ErrorCode.CAPABILITY_DENIED):
            self.make_validation(status=ValidationStatus.REJECTED, reason_code=code)
        for code in (None, ErrorCode.PROVIDER_TIMEOUT, ErrorCode.RATE_LIMITED, ErrorCode.ACCESS_DENIED):
            with self.subTest(rejected=repr(code)), self.assertRaises(ValueError):
                self.make_validation(status=ValidationStatus.REJECTED, reason_code=code)
        for code in (ErrorCode.PROVIDER_TIMEOUT, ErrorCode.OPERATION_TIMEOUT, ErrorCode.CAPACITY_EXCEEDED,
                     ErrorCode.QUOTA_EXCEEDED, ErrorCode.CREDENTIAL_UNAVAILABLE):
            self.make_validation(status=ValidationStatus.INDETERMINATE, reason_code=code)
        for code in (None, ErrorCode.CREDENTIAL_REJECTED, ErrorCode.CAPABILITY_DENIED):
            with self.subTest(indeterminate=repr(code)), self.assertRaises(ValueError):
                self.make_validation(status=ValidationStatus.INDETERMINATE, reason_code=code)

    def test_checked_at_must_be_utc(self):
        with self.assertRaises(ValueError):
            self.make_validation(checked_at=datetime(2026, 10, 23, 12, 0))

    def test_probe_outcome_uses_same_rules(self):
        usage = UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini")
        ProbeOutcome(ValidationStatus.VALID, None, usage)
        ProbeOutcome(ValidationStatus.REJECTED, ErrorCode.CREDENTIAL_REJECTED, usage)
        with self.assertRaises(ValueError):
            ProbeOutcome(ValidationStatus.REJECTED, ErrorCode.PROVIDER_UNAVAILABLE, usage)
        with self.assertRaises(TypeError):
            ProbeOutcome(ValidationStatus.VALID, None, None)  # type: ignore[arg-type]

    def test_step_output(self):
        usage = UsageEntry(Operation.TRANSCRIBE_AUDIO, "gpt-4o-mini-transcribe")
        self.assertEqual(StepOutput("", usage).text, "")
        self.assertNotIn(CONTENT_CANARY, repr(StepOutput(CONTENT_CANARY, usage)))
        with self.assertRaises(TypeError):
            StepOutput(None, usage)  # type: ignore[arg-type]


class ErrorTests(unittest.TestCase):
    def test_message_is_fixed(self):
        error = ProviderIntegrationError(ErrorCode.RATE_LIMITED)
        self.assertEqual(str(error), SAFE_MESSAGES[ErrorCode.RATE_LIMITED])
        self.assertIs(error.code, ErrorCode.RATE_LIMITED)
        with self.assertRaises(TypeError):
            ProviderIntegrationError("RATE_LIMITED")  # type: ignore[arg-type]

    def test_chained_exceptions_are_hidden(self):
        for explicit in (True, False):
            with self.subTest(explicit_from=explicit):
                try:
                    try:
                        raise ValueError(f"sdk failure with {KEY_CANARY} and {CONTENT_CANARY}")
                    except ValueError as inner:
                        if explicit:
                            raise ProviderIntegrationError(ErrorCode.PROVIDER_UNAVAILABLE) from inner
                        raise ProviderIntegrationError(ErrorCode.PROVIDER_UNAVAILABLE)
                except ProviderIntegrationError as caught:
                    rendered = "".join(traceback.format_exception(caught))
                    self.assertIsNone(caught.__cause__)
                    self.assertIsNone(caught.__context__)
                self.assertNotIn(KEY_CANARY, rendered)
                self.assertNotIn(CONTENT_CANARY, rendered)

    def test_operation_error_carries_usage(self):
        usage = UsageEntry(Operation.TRANSCRIBE_AUDIO, "gpt-4o-mini-transcribe", audio_seconds=1.0)
        error = ProviderOperationError(ErrorCode.PROVIDER_TIMEOUT, usage)
        self.assertIs(error.usage, usage)
        self.assertIsInstance(error, ProviderIntegrationError)
        self.assertIsNone(ProviderOperationError(ErrorCode.PROVIDER_TIMEOUT).usage)
        with self.assertRaises(TypeError):
            ProviderOperationError(ErrorCode.PROVIDER_TIMEOUT, {"audio_seconds": 1.0})  # type: ignore[arg-type]


class ErrorSerializationTests(unittest.TestCase):
    """R3 (review fix F1): safe errors survive pickle/copy with code, usage and fixed message only."""

    def test_errors_round_trip_pickle_and_copy(self):
        usage = UsageEntry(Operation.TRANSCRIBE_AUDIO, "gpt-4o-mini-transcribe", audio_seconds=1.0)
        try:
            try:
                raise ValueError(f"sdk detail {KEY_CANARY}")
            except ValueError as inner:
                raise ProviderOperationError(ErrorCode.PROVIDER_TIMEOUT, usage) from inner
        except ProviderOperationError as chained:
            operation_error = chained
        for original in (ProviderIntegrationError(ErrorCode.RATE_LIMITED), operation_error):
            pickled = pickle.dumps(original)
            self.assertNotIn(KEY_CANARY.encode(), pickled)
            for clone in (pickle.loads(pickled), copy.copy(original), copy.deepcopy(original)):
                with self.subTest(kind=type(original).__name__):
                    self.assertIs(type(clone), type(original))
                    self.assertIs(clone.code, original.code)
                    self.assertEqual(str(clone), SAFE_MESSAGES[original.code])
                    self.assertIsNone(clone.__cause__)
                    if isinstance(original, ProviderOperationError):
                        self.assertEqual(clone.usage, usage)


class LimitProfileTests(unittest.TestCase):
    def test_local_profile_matches_accepted_l5(self):
        expected = dict(
            max_text_bytes=65_536, max_prompt_bytes=131_072, max_transcript_bytes=131_072,
            max_audio_bytes=10_485_760, max_generation_bytes=65_536, max_response_body_bytes=1_048_576,
            invocation_timeout_seconds=90, validation_timeout_seconds=20, verify_timeout_seconds=5,
            admit_timeout_seconds=5, generation_call_timeout_seconds=30, transcription_call_timeout_seconds=60,
            validation_call_timeout_seconds=15, connect_timeout_seconds=5, cleanup_timeout_seconds=2,
            max_concurrent_operations=8, max_retries=0, follow_redirects=False,
        )
        self.assertEqual(limit_values(), expected)

    def test_from_mapping_round_trip_and_field_rules(self):
        self.assertEqual(LimitProfile.from_mapping(limit_values()), LOCAL_LIMIT_PROFILE)
        with self.assertRaises(ValueError):
            LimitProfile.from_mapping(limit_values(max_retires=0))
        missing = limit_values()
        del missing["max_audio_bytes"]
        with self.assertRaises(ValueError):
            LimitProfile.from_mapping(missing)
        with self.assertRaises(TypeError):
            LimitProfile.from_mapping([("max_text_bytes", 1)])  # type: ignore[arg-type]

    def test_zero_negative_and_malformed_values_rejected(self):
        for f in dataclasses.fields(LimitProfile):
            if f.name in ("max_retries", "follow_redirects"):
                continue
            for bad in (0, -1, True, "5", float("nan"), float("inf"), None):
                with self.subTest(field=f.name, value=repr(bad)), self.assertRaises(ValueError):
                    LimitProfile(**limit_values(**{f.name: bad}))

    def test_byte_limits_require_int(self):
        with self.assertRaises(ValueError):
            LimitProfile(**limit_values(max_text_bytes=65_536.0))

    def test_retries_and_redirects_fixed(self):
        for bad in (1, -1, True, None):
            with self.subTest(retries=repr(bad)), self.assertRaises(ValueError):
                LimitProfile(**limit_values(max_retries=bad))
        for bad in (True, 0, None):
            with self.subTest(redirects=repr(bad)), self.assertRaises(ValueError):
                LimitProfile(**limit_values(follow_redirects=bad))

    def test_cross_field_boundaries(self):
        # N-1 / N / N+1 around the validation deadline for the validation call timeout.
        LimitProfile(**limit_values(validation_call_timeout_seconds=19))
        LimitProfile(**limit_values(validation_call_timeout_seconds=20))
        with self.assertRaises(ValueError):
            LimitProfile(**limit_values(validation_call_timeout_seconds=21))
        for name in ("verify_timeout_seconds", "admit_timeout_seconds"):
            LimitProfile(**limit_values(**{name: 20}))
            with self.subTest(field=name), self.assertRaises(ValueError):
                LimitProfile(**limit_values(**{name: 21}))
        with self.assertRaises(ValueError):
            LimitProfile(**limit_values(transcription_call_timeout_seconds=91))
        with self.assertRaises(ValueError):
            LimitProfile(**limit_values(connect_timeout_seconds=16))


class ProviderConfigTests(unittest.TestCase):
    def test_destination_must_be_plain_https(self):
        make_provider_config()
        for bad in (
            "http://provider.example.test/v1/",
            "https://user:pass@provider.example.test/v1/",
            "https://provider.example.test/v1/?redirect=evil",
            "https://provider.example.test/v1/#frag",
            "https:///v1/",
            " https://provider.example.test/v1/",
            "",
            None,
        ):
            with self.subTest(destination=repr(bad)[:24]), self.assertRaises(ValueError):
                make_provider_config(destination=bad)

    def test_targets_and_settings_validated(self):
        with self.assertRaises(TypeError):
            make_provider_config(targets=frozenset())
        with self.assertRaises(ValueError):
            make_provider_config(provider="Open AI")
        for overrides in ({"max_tokens": 0}, {"max_tokens": True}, {"temperature": -0.1},
                          {"temperature": float("nan")}, {"system_prompt": "  "}):
            with self.subTest(overrides=list(overrides)), self.assertRaises(ValueError):
                make_generation_settings(**overrides)

    def test_from_mapping_rejects_unknown_fields(self):
        data = {
            "provider": "openai",
            "destination": "https://provider.example.test/v1/",
            "targets": [{"operation": "generate_text", "model": "gpt-4o-mini"}],
            "generation": {"max_tokens": 256, "temperature": 0.4, "system_prompt": "Synthetic system prompt."},
        }
        config = ProviderConfig.from_mapping(data)
        self.assertTrue(config.supports(GEN))
        self.assertFalse(config.supports(TRANSCRIBE))
        for mutate in (
            lambda d: d.update(base_url="https://evil.example.test/"),
            lambda d: d["targets"][0].update(authorized=True),
            lambda d: d["targets"][0].update(operation="list_models"),
            lambda d: d["generation"].update(max_retries=3),
            lambda d: d.pop("destination"),
        ):
            candidate = copy.deepcopy(data)
            mutate(candidate)
            with self.subTest(case=str(candidate)[:40]), self.assertRaises((ValueError, TypeError)):
                ProviderConfig.from_mapping(candidate)

    def test_module_config_is_immutable_snapshot(self):
        providers = {"openai": make_provider_config()}
        config = ModuleConfig(limits=LOCAL_LIMIT_PROFILE, providers=providers)
        providers["other"] = make_provider_config(provider="other")
        self.assertNotIn("other", config.providers)
        with self.assertRaises(TypeError):
            config.providers["other"] = make_provider_config(provider="other")  # type: ignore[index]
        with self.assertRaises(ValueError):
            ModuleConfig(limits=LOCAL_LIMIT_PROFILE, providers={"alias": make_provider_config()})
        with self.assertRaises(TypeError):
            ModuleConfig(limits=limit_values(), providers={})  # type: ignore[arg-type]


class PortTests(unittest.TestCase):
    def test_protocol_methods_and_async_shape(self):
        expected = {
            ContextVerifier: {"verify": True},
            CredentialReader: {"admit": False},
            ProviderSession: {"generate_text": True, "transcribe_audio": True, "validate_access": True},
            ProviderAdapter: {"supported_operations": False, "open_session": False},
        }
        for protocol, methods in expected.items():
            for name, is_async in methods.items():
                with self.subTest(protocol=protocol.__name__, method=name):
                    self.assertEqual(inspect.iscoroutinefunction(getattr(protocol, name)), is_async)

    def test_session_signatures(self):
        self.assertEqual(
            list(inspect.signature(ProviderSession.transcribe_audio).parameters),
            ["self", "target", "audio", "audio_format", "remaining_seconds"],
        )
        self.assertEqual(
            list(inspect.signature(ContextVerifier.verify).parameters),
            ["self", "call_evidence", "requested_binding", "kind", "targets"],
        )

    def test_incomplete_implementation_is_not_an_adapter(self):
        class Partial:
            def supported_operations(self):
                return frozenset()

        self.assertNotIsInstance(Partial(), ProviderAdapter)


class ImportSafetyTests(unittest.TestCase):
    def test_package_source_has_no_env_sdk_or_network_use(self):
        """TC-14 (core part): shared modules never read env keys, load dotenv or import SDKs."""
        forbidden = ("os.environ", "getenv", "dotenv", "OPENAI_API_KEY", "import openai", "from openai",
                     "import httpx", "import requests", "import socket", "fastapi")
        adapter_tokens = ("provider_integration.adapters", "from .adapters", "import adapters")
        for path in sorted(PACKAGE_DIR.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            # L1: wiring.py is the single composition module allowed to reference adapters
            # (checked separately below to be lazy); every other core module must not.
            tokens = forbidden if path.name == "wiring.py" else forbidden + adapter_tokens
            for token in tokens:
                with self.subTest(file=path.name, token=token):
                    self.assertNotIn(token, source)

    def test_wiring_imports_adapters_only_lazily(self):
        """T4.1 (C5/C6): no module-level adapter import anywhere in the core package."""
        import ast

        for path in sorted(PACKAGE_DIR.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [node.module or ""] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
                    with self.subTest(file=path.name, line=node.lineno):
                        self.assertFalse(any("adapters" in name for name in names))

    def test_import_without_key_or_network(self):
        """Import in a clean subprocess with no OPENAI_API_KEY and sockets disabled."""
        env = {name: os.environ[name] for name in ("SYSTEMROOT", "PATH", "TEMP", "TMP") if name in os.environ}
        script = (
            "import sys\n"
            f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
            "import socket\n"
            "def deny(*a, **k):\n"
            "    raise RuntimeError('network denied')\n"
            "socket.socket.connect = deny\n"
            "socket.create_connection = deny\n"
            "import services.provider_integration as pi\n"
            "loaded = sorted(m for m in ('openai', 'httpx', 'dotenv', 'fastapi', 'requests',"
            " 'services.provider_integration.adapters') if m in sys.modules)\n"
            "print('loaded=' + ','.join(loaded))\n"
            "print('exports=' + str(len(pi.__all__)))\n"
        )
        completed = subprocess.run(
            [sys.executable, "-I", "-c", script],
            env=env, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60, check=False,
        )
        self.assertEqual(completed.returncode, 0, "import subprocess failed")
        self.assertIn("loaded=\n", completed.stdout)
        self.assertNotIn("OPENAI_API_KEY", env)


if __name__ == "__main__":
    unittest.main()
