"""Allowlisted failure codes and fixed safe messages (L2).

Messages come only from the fixed code-to-message map below. Do not
interpolate identifiers, filenames, exception text or model output into them.
"""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Mapping, Optional

if TYPE_CHECKING:
    from services.provider_integration.types import UsageEntry


class ErrorCode(str, Enum):
    """Internal safe failure categories. No HTTP status is implied (B6)."""

    INVALID_INPUT = "INVALID_INPUT"
    ACCESS_DENIED = "ACCESS_DENIED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    CREDENTIAL_UNAVAILABLE = "CREDENTIAL_UNAVAILABLE"
    CREDENTIAL_REJECTED = "CREDENTIAL_REJECTED"
    CAPABILITY_DENIED = "CAPABILITY_DENIED"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    PROVIDER_RESPONSE_INVALID = "PROVIDER_RESPONSE_INVALID"
    OPERATION_TIMEOUT = "OPERATION_TIMEOUT"
    CAPACITY_EXCEEDED = "CAPACITY_EXCEEDED"


SAFE_MESSAGES: Mapping[ErrorCode, str] = MappingProxyType(
    {
        ErrorCode.INVALID_INPUT: "The request input is missing, malformed, oversized or unsupported.",
        ErrorCode.ACCESS_DENIED: "Access was denied.",
        ErrorCode.NOT_CONFIGURED: "The requested provider configuration is not available.",
        ErrorCode.CREDENTIAL_UNAVAILABLE: "The selected credential is not available.",
        ErrorCode.CREDENTIAL_REJECTED: "The provider rejected the selected credential.",
        ErrorCode.CAPABILITY_DENIED: "The selected credential cannot use the requested model or operation.",
        ErrorCode.UNSUPPORTED_OPERATION: "The requested provider, model or operation is not supported.",
        ErrorCode.RATE_LIMITED: "The provider rate limit was reached.",
        ErrorCode.QUOTA_EXCEEDED: "The provider quota or spending limit was reached.",
        ErrorCode.PROVIDER_TIMEOUT: "The provider did not respond in time.",
        ErrorCode.PROVIDER_UNAVAILABLE: "The provider is temporarily unavailable.",
        ErrorCode.INTERNAL_ERROR: "An internal error occurred.",
        ErrorCode.PROVIDER_RESPONSE_INVALID: "The provider returned an unusable response.",
        ErrorCode.OPERATION_TIMEOUT: "The operation did not complete in time.",
        ErrorCode.CAPACITY_EXCEEDED: "The service is at capacity; try again later.",
    }
)


def safe_message(code: ErrorCode) -> str:
    """Return the fixed safe message for an allowlisted code."""
    if not isinstance(code, ErrorCode):
        raise TypeError("code must be an ErrorCode")
    return SAFE_MESSAGES[code]


_BASE_CAUSE = BaseException.__dict__["__cause__"]
_BASE_CONTEXT = BaseException.__dict__["__context__"]


class ProviderIntegrationError(Exception):
    """Safe failure carrying only an allowlisted code and its fixed message.

    Chained exceptions are hidden: ``__cause__`` and ``__context__`` always read
    as ``None`` and clear the underlying reference when read, so tracebacks and
    loggers do not render a raw SDK exception. Raise with ``from None`` anyway;
    this is defense in depth, not a guarantee against every inspection path.
    """

    def __init__(self, code: ErrorCode) -> None:
        if not isinstance(code, ErrorCode):
            raise TypeError("code must be an ErrorCode")
        super().__init__(SAFE_MESSAGES[code])
        self.code = code

    def __reduce__(self) -> tuple:
        # Rebuild from the code only (R3): the fixed message is derived, causes stay hidden.
        return (type(self), (self.code,))

    @property
    def __cause__(self) -> None:
        _BASE_CAUSE.__set__(self, None)
        return None

    @__cause__.setter
    def __cause__(self, value: object) -> None:
        _BASE_CAUSE.__set__(self, None)

    @property
    def __context__(self) -> None:
        _BASE_CONTEXT.__set__(self, None)
        return None

    @__context__.setter
    def __context__(self, value: object) -> None:
        _BASE_CONTEXT.__set__(self, None)


class ProviderOperationError(ProviderIntegrationError):
    """Raised by a ProviderSession when an attempted provider step fails.

    ``usage`` is the UsageEntry for the attempted step (quantities may be null),
    so the orchestrator can retain usage for steps that reached the provider.
    """

    def __init__(self, code: ErrorCode, usage: Optional["UsageEntry"] = None) -> None:
        from services.provider_integration.types import UsageEntry

        if usage is not None and not isinstance(usage, UsageEntry):
            raise TypeError("usage must be a UsageEntry or None")
        super().__init__(code)
        self.usage = usage

    def __reduce__(self) -> tuple:
        return (type(self), (self.code, self.usage))
