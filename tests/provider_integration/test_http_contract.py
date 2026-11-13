"""T4.6: HTTP status and body mapping for the future endpoints (D-2, B6.23).

Pure mapping only: no route is registered and nothing is sent anywhere. Bodies
must contain only allowlisted fields and never reflect provider details, keys
or caller-supplied identifiers.
"""

import json
import unittest

from services.provider_integration import (
    BoundaryFailure,
    ErrorCode,
    FileType,
    InvocationResult,
    Operation,
    Outcome,
    UsageEntry,
    new_request_id,
)
from services.provider_integration.http_contract import (
    ERROR_FIELDS,
    MESSAGES,
    STATUS_BY_CODE,
    SUCCESS_FIELDS,
    to_http,
)

CANARY = "test-provider-key-canary-do-not-reflect"
EXPECTED_STATUS = {
    ErrorCode.INVALID_INPUT: 400,
    ErrorCode.UNSUPPORTED_OPERATION: 400,
    ErrorCode.ACCESS_DENIED: 403,
    ErrorCode.CREDENTIAL_UNAVAILABLE: 403,
    ErrorCode.CREDENTIAL_REJECTED: 403,
    ErrorCode.CAPABILITY_DENIED: 403,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.QUOTA_EXCEEDED: 429,
    ErrorCode.CAPACITY_EXCEEDED: 429,
    ErrorCode.NOT_CONFIGURED: 503,
    ErrorCode.PROVIDER_UNAVAILABLE: 503,
    ErrorCode.PROVIDER_RESPONSE_INVALID: 502,
    ErrorCode.PROVIDER_TIMEOUT: 504,
    ErrorCode.OPERATION_TIMEOUT: 504,
    ErrorCode.INTERNAL_ERROR: 500,
}


def success(usage=(), file_type=FileType.TEXT):
    return InvocationResult(
        request_id=new_request_id(), provider="openai", model="gpt-4o-mini", file_type=file_type,
        outcome=Outcome.SUCCESS, result="Synthetic answer", usage=usage,
    )


def failure(code, usage=()):
    return InvocationResult(
        request_id=new_request_id(), provider="openai", model="gpt-4o-mini", file_type=FileType.TEXT,
        outcome=Outcome.ERROR, error_code=code, usage=usage,
    )


class ErrorMappingTests(unittest.TestCase):
    def test_every_error_code_has_exactly_the_agreed_status(self):
        self.assertEqual(set(STATUS_BY_CODE), set(ErrorCode), "every code needs a reviewed status")
        self.assertEqual(dict(STATUS_BY_CODE), EXPECTED_STATUS)
        for code in ErrorCode:
            with self.subTest(code=code.value):
                status, body = to_http(failure(code))
                self.assertEqual(status, EXPECTED_STATUS[code])
                self.assertEqual(set(body), ERROR_FIELDS)
                self.assertEqual(body["error_code"], code.value)
                self.assertEqual(body["message"], MESSAGES[code])

    def test_messages_are_fixed_short_and_non_revealing(self):
        self.assertEqual(set(MESSAGES), set(ErrorCode))
        for code, message in MESSAGES.items():
            with self.subTest(code=code.value):
                self.assertIsInstance(message, str)
                self.assertTrue(0 < len(message) <= 120)
                for word in ("openai", "key", "sk-", "scope", "credential-", "version"):
                    self.assertNotIn(word, message.lower())

    def test_all_access_denials_share_one_message(self):
        """B3.11: one generic denial; 401 and 403 differ only in status."""
        denials = (ErrorCode.ACCESS_DENIED, ErrorCode.CREDENTIAL_UNAVAILABLE,
                   ErrorCode.CREDENTIAL_REJECTED, ErrorCode.CAPABILITY_DENIED)
        self.assertEqual(len({MESSAGES[code] for code in denials}), 1)

    def test_missing_service_auth_is_401_with_the_same_body(self):
        boundary = BoundaryFailure.create(ErrorCode.ACCESS_DENIED)
        status, body = to_http(boundary, service_auth_missing=True)
        self.assertEqual(status, 401)
        self.assertEqual(body, {"error_code": "ACCESS_DENIED", "message": MESSAGES[ErrorCode.ACCESS_DENIED],
                                "request_id": boundary.request_id})
        self.assertEqual(to_http(boundary)[0], 403)

    def test_service_auth_flag_only_applies_to_access_denied(self):
        with self.assertRaises(ValueError):
            to_http(BoundaryFailure.create(ErrorCode.INVALID_INPUT), service_auth_missing=True)
        with self.assertRaises(ValueError):
            to_http(success(), service_auth_missing=True)

    def test_boundary_failures_map_like_results(self):
        for code in (ErrorCode.INVALID_INPUT, ErrorCode.ACCESS_DENIED):
            with self.subTest(code=code.value):
                boundary = BoundaryFailure.create(code)
                status, body = to_http(boundary)
                self.assertEqual(status, EXPECTED_STATUS[code])
                self.assertEqual(body["request_id"], boundary.request_id)

    def test_error_body_leaks_no_usage_model_or_provider(self):
        usage = (UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini", total_tokens=7, provider_request_id="req_err_1"),)
        status, body = to_http(failure(ErrorCode.CREDENTIAL_REJECTED, usage))
        serialized = json.dumps(body)
        for absent in ("req_err_1", "gpt-4o-mini", "openai", "total_tokens"):
            self.assertNotIn(absent, serialized)


class SuccessMappingTests(unittest.TestCase):
    def test_success_body_matches_backend_format(self):
        """B6.23: result, model, file_type, total_tokens, provider_request_id (+ request_id)."""
        usage = (UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini", input_tokens=10, output_tokens=5,
                            total_tokens=15, provider_request_id="req_chat_1"),)
        result = success(usage)
        status, body = to_http(result)
        self.assertEqual(status, 200)
        self.assertEqual(set(body), SUCCESS_FIELDS)
        self.assertEqual(body, {"result": "Synthetic answer", "model": "gpt-4o-mini", "file_type": "text",
                                "total_tokens": 15, "provider_request_id": "req_chat_1",
                                "request_id": result.request_id})
        json.dumps(body)

    def test_generation_step_supplies_usage_for_audio(self):
        usage = (
            UsageEntry(Operation.TRANSCRIBE_AUDIO, "gpt-4o-mini-transcribe", total_tokens=40, provider_request_id="req_tr_1"),
            UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini", total_tokens=15, provider_request_id="req_chat_1"),
        )
        status, body = to_http(success(usage, file_type=FileType.AUDIO))
        self.assertEqual((status, body["file_type"], body["total_tokens"], body["provider_request_id"]),
                         (200, "audio", 15, "req_chat_1"))

    def test_unreported_usage_is_null_not_zero(self):
        for usage in ((), (UsageEntry(Operation.GENERATE_TEXT, "gpt-4o-mini"),)):
            with self.subTest(usage=len(usage)):
                _, body = to_http(success(usage))
                self.assertIsNone(body["total_tokens"])
                self.assertIsNone(body["provider_request_id"])

    def test_unknown_result_types_are_refused(self):
        for bad in (None, {"result": "x"}, CANARY, object()):
            with self.subTest(value=type(bad).__name__), self.assertRaises(TypeError):
                to_http(bad)


if __name__ == "__main__":
    unittest.main()
