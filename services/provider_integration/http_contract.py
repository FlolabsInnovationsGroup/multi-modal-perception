"""HTTP status and body mapping for the future endpoints (T4.6; D-2, B6.23).

Pure functions only: this module registers no route, imports no web framework
and performs no I/O. A future approved route calls ``to_http`` with a module
result and sends the returned status and body unchanged.

D-2 (lead decision, 2026-11-13; backend agreement pending):

- Errors: ``{"error_code", "message", "request_id"}``. ``error_code`` is the
  module's allowlisted code; ``message`` is a fixed sentence per code. Nothing
  from the provider, the key or the caller's identifiers is included.
- All access-type denials share one message (B3.11). A missing or unreadable
  service token is 401; every other denial is 403 with the same body shape.
- Success: ``result``, ``model``, ``file_type`` (as today) plus ``total_tokens``
  and ``provider_request_id`` from the generation step (B6.23) and the local
  ``request_id``. Unreported usage is null, never zero.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Dict, Optional, Tuple, Union

from datetime import timezone

from services.provider_integration.errors import ErrorCode
from services.provider_integration.types import (
    BoundaryFailure,
    InvocationResult,
    Operation,
    Outcome,
    ValidationResult,
    new_request_id,
)

ERROR_FIELDS = frozenset({"error_code", "message", "request_id"})
SUCCESS_FIELDS = frozenset({"result", "model", "file_type", "total_tokens", "provider_request_id", "request_id"})

_DENIED = "Access denied."

STATUS_BY_CODE = MappingProxyType({
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
})

MESSAGES = MappingProxyType({
    ErrorCode.INVALID_INPUT: "The request is invalid.",
    ErrorCode.UNSUPPORTED_OPERATION: "The requested model or operation is not supported.",
    ErrorCode.ACCESS_DENIED: _DENIED,
    ErrorCode.CREDENTIAL_UNAVAILABLE: _DENIED,
    ErrorCode.CREDENTIAL_REJECTED: _DENIED,
    ErrorCode.CAPABILITY_DENIED: _DENIED,
    ErrorCode.RATE_LIMITED: "The provider rate limit was reached. Try again later.",
    ErrorCode.QUOTA_EXCEEDED: "The provider usage quota is exhausted.",
    ErrorCode.CAPACITY_EXCEEDED: "The service is busy. Try again later.",
    ErrorCode.NOT_CONFIGURED: "The service is not configured for this request.",
    ErrorCode.PROVIDER_UNAVAILABLE: "The provider is temporarily unavailable.",
    ErrorCode.PROVIDER_RESPONSE_INVALID: "The provider returned an invalid response.",
    ErrorCode.PROVIDER_TIMEOUT: "The provider did not respond in time.",
    ErrorCode.OPERATION_TIMEOUT: "The request did not finish in time.",
    ErrorCode.INTERNAL_ERROR: "An internal error occurred.",
})

Body = Dict[str, object]


def _error(code: ErrorCode, request_id: str, status: int) -> Tuple[int, Body]:
    return status, {"error_code": code.value, "message": MESSAGES[code], "request_id": request_id}


def _generation_usage(result: InvocationResult) -> Tuple[Optional[int], Optional[str]]:
    for entry in result.usage:
        if entry.operation is Operation.GENERATE_TEXT:
            return entry.total_tokens, entry.provider_request_id
    return None, None


def to_http(
    result: Union[InvocationResult, BoundaryFailure], *, service_auth_missing: bool = False
) -> Tuple[int, Body]:
    """Return ``(status, body)`` for one invocation outcome.

    ``service_auth_missing`` is set by the route only when the service token is
    absent or unreadable; it turns ACCESS_DENIED into 401 and is refused otherwise.
    """
    if not isinstance(result, (InvocationResult, BoundaryFailure)):
        raise TypeError("result must be an InvocationResult or BoundaryFailure")
    if service_auth_missing and result.error_code is not ErrorCode.ACCESS_DENIED:
        raise ValueError("service_auth_missing applies only to ACCESS_DENIED")
    if result.outcome is not Outcome.SUCCESS:
        code = result.error_code
        status = 401 if service_auth_missing else STATUS_BY_CODE[code]  # type: ignore[index]
        return _error(code, result.request_id, status)  # type: ignore[arg-type]
    total_tokens, provider_request_id = _generation_usage(result)  # type: ignore[arg-type]
    return 200, {
        "result": result.result,
        "model": result.model,  # type: ignore[union-attr]
        "file_type": result.file_type.value,  # type: ignore[union-attr]
        "total_tokens": total_tokens,
        "provider_request_id": provider_request_id,
        "request_id": result.request_id,
    }


VALIDATION_FIELDS = frozenset(
    {"status", "reason_code", "checked_at", "credential_version", "provider_request_id", "request_id"}
)


def error_response(code: ErrorCode) -> Tuple[int, Body]:
    """Status and body for a failure that happens before any result exists (for example
    NOT_CONFIGURED when the service lacks its live settings). Uses a new request ID."""
    if not isinstance(code, ErrorCode):
        raise TypeError("code must be an ErrorCode")
    return _error(code, new_request_id(), STATUS_BY_CODE[code])


def validation_to_http(
    result: Union[ValidationResult, BoundaryFailure], *, service_auth_missing: bool = False
) -> Tuple[int, Body]:
    """Return ``(status, body)`` for a validation outcome (P-1 section 5, B5.20 fields).

    A completed check is 200 whatever its status (valid, rejected or indeterminate);
    only boundary failures use the error format.
    """
    if isinstance(result, BoundaryFailure):
        return to_http(result, service_auth_missing=service_auth_missing)
    if not isinstance(result, ValidationResult):
        raise TypeError("result must be a ValidationResult or BoundaryFailure")
    if service_auth_missing:
        raise ValueError("service_auth_missing applies only to ACCESS_DENIED")
    provider_request_id = next((u.provider_request_id for u in result.usage if u.provider_request_id), None)
    checked_at = result.checked_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return 200, {
        "status": result.status.value,
        "reason_code": result.reason_code.value if result.reason_code is not None else None,
        "checked_at": checked_at,
        "credential_version": result.binding.credential_version,
        "provider_request_id": provider_request_id,
        "request_id": result.request_id,
    }
