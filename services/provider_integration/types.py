"""Internal immutable request/result types and the secret holder (L2).

These are in-process types, not a public JSON API. Construction validates
shape and invariants only; it does not authenticate anything. A VerifiedContext
must come from the injected ContextVerifier, never from caller-supplied fields.
Nothing here performs I/O or reads the environment.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import FrozenSet, Optional, Tuple

from services.provider_integration.errors import ErrorCode

MAX_IDENTIFIER_LENGTH = 128
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}")


def is_valid_identifier(value: object) -> bool:
    """True for a nonempty ASCII ``[A-Za-z0-9._:-]`` string of at most 128 characters."""
    return (
        isinstance(value, str)
        and value.isascii()
        and _IDENTIFIER_PATTERN.fullmatch(value) is not None
    )


def _require_identifier(value: object, name: str) -> None:
    # The message names the field only; it never reflects the untrusted value.
    if not is_valid_identifier(value):
        raise ValueError(f"{name} is not a valid identifier")


def _require_instance(value: object, expected: type, name: str) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"{name} must be a {expected.__name__}")


def _require_utc(value: object, name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")


def _require_target_set(value: object, name: str) -> None:
    if not isinstance(value, frozenset) or not value:
        raise TypeError(f"{name} must be a nonempty frozenset of Target")
    if not all(isinstance(item, Target) for item in value):
        raise TypeError(f"{name} must contain only Target values")


def new_request_id() -> str:
    """Generate a local correlation ID (UUID4 string)."""
    return str(uuid.uuid4())


class Operation(str, Enum):
    GENERATE_TEXT = "generate_text"
    TRANSCRIBE_AUDIO = "transcribe_audio"


class CredentialSource(str, Enum):
    CUSTOMER = "customer"
    PLATFORM = "platform"


class ContextKind(str, Enum):
    INVOKE = "invoke"
    VALIDATE = "validate"


class CredentialState(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    DISABLED = "disabled"
    DELETED = "deleted"
    EXPIRED = "expired"


class Outcome(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


class ValidationStatus(str, Enum):
    VALID = "valid"
    REJECTED = "rejected"
    INDETERMINATE = "indeterminate"


class FileType(str, Enum):
    TEXT = "text"
    AUDIO = "audio"


class AudioFormat(str, Enum):
    WAV = "wav"
    MP3 = "mp3"
    M4A = "m4a"
    WEBM = "webm"
    MP4 = "mp4"
    MPEG = "mpeg"
    MPGA = "mpga"


class SecretValue:
    """Request-local holder for a provider credential.

    repr/str/format are constant and redacted; equality is identity; pickling,
    copying and serialization are refused. Python cannot guarantee the plaintext
    is zeroized from memory; keep the holder's lifetime to one operation.
    """

    __slots__ = ("__value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError("secret value must be a nonempty string without surrounding whitespace")
        object.__setattr__(self, "_SecretValue__value", value)

    def reveal_for_session(self) -> str:
        """Return the plaintext. Only a ProviderSession implementation may call this."""
        return self.__value

    def appears_in(self, text: object) -> bool:
        """True if the exact secret occurs in ``text`` (defense-in-depth output check)."""
        return isinstance(text, str) and self.__value in text

    def __repr__(self) -> str:
        return "SecretValue(<redacted>)"

    __str__ = __repr__

    def __format__(self, format_spec: str) -> str:
        return repr(self)

    def __eq__(self, other: object) -> bool:
        return self is other

    def __hash__(self) -> int:
        return id(self)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("SecretValue is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("SecretValue is immutable")

    def __reduce_ex__(self, protocol: object) -> object:
        raise TypeError("SecretValue cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("SecretValue cannot be serialized")

    def __getstate__(self) -> object:
        raise TypeError("SecretValue cannot be serialized")

    def __copy__(self) -> "SecretValue":
        raise TypeError("SecretValue cannot be copied")

    def __deepcopy__(self, memo: object) -> "SecretValue":
        raise TypeError("SecretValue cannot be copied")


def sanitize_provider_request_id(
    value: object, secret: Optional[SecretValue] = None
) -> Optional[str]:
    """Keep a provider request ID only if it passes the ID rule and omits the key."""
    if not is_valid_identifier(value):
        return None
    if secret is not None and secret.appears_in(value):
        return None
    return value  # type: ignore[return-value]


@dataclass(frozen=True)
class Binding:
    """Trusted request-to-credential binding. Opaque IDs compare exactly; no case-folding."""

    scope_id: str
    credential_ref: str
    credential_version: str
    credential_source: CredentialSource
    provider: str

    def __post_init__(self) -> None:
        for name in ("scope_id", "credential_ref", "credential_version", "provider"):
            _require_identifier(getattr(self, name), name)
        _require_instance(self.credential_source, CredentialSource, "credential_source")


@dataclass(frozen=True)
class Target:
    operation: Operation
    model: str

    def __post_init__(self) -> None:
        _require_instance(self.operation, Operation, "operation")
        _require_identifier(self.model, "model")


@dataclass(frozen=True)
class VerifiedContext:
    """Context returned only by the injected ContextVerifier after verification."""

    binding: Binding
    request_id: str
    kind: ContextKind
    allowed_targets: FrozenSet[Target]
    expires_at: datetime

    def __post_init__(self) -> None:
        _require_instance(self.binding, Binding, "binding")
        _require_identifier(self.request_id, "request_id")
        _require_instance(self.kind, ContextKind, "kind")
        _require_target_set(self.allowed_targets, "allowed_targets")
        _require_utc(self.expires_at, "expires_at")

    def is_expired(self, now: datetime) -> bool:
        _require_utc(now, "now")
        return now >= self.expires_at

    def permits(self, target: Target) -> bool:
        return isinstance(target, Target) and target in self.allowed_targets


@dataclass(frozen=True)
class InvocationInput:
    """Content for one invocation. Caller filenames are not part of this type."""

    text: str = field(repr=False)
    audio: Optional[bytes] = field(default=None, repr=False)
    audio_format: Optional[AudioFormat] = None

    def __post_init__(self) -> None:
        _require_instance(self.text, str, "text")
        if self.audio is not None and type(self.audio) is not bytes:
            raise TypeError("audio must be bytes or None")
        if self.has_audio:
            _require_instance(self.audio_format, AudioFormat, "audio_format")
        else:
            if self.audio_format is not None:
                raise ValueError("audio_format requires nonempty audio")
            if not self.text.strip():
                raise ValueError("text or audio is required")

    @property
    def has_audio(self) -> bool:
        return bool(self.audio)


@dataclass(frozen=True)
class InvocationRequest:
    content: InvocationInput
    generation_target: Target
    transcription_target: Optional[Target] = None

    def __post_init__(self) -> None:
        _require_instance(self.content, InvocationInput, "content")
        _require_instance(self.generation_target, Target, "generation_target")
        if self.generation_target.operation is not Operation.GENERATE_TEXT:
            raise ValueError("generation_target must be a generate_text target")
        if self.content.has_audio:
            _require_instance(self.transcription_target, Target, "transcription_target")
            if self.transcription_target.operation is not Operation.TRANSCRIBE_AUDIO:
                raise ValueError("transcription_target must be a transcribe_audio target")
        elif self.transcription_target is not None:
            raise ValueError("text-only requests must not include a transcription_target")

    @property
    def targets(self) -> FrozenSet[Target]:
        if self.transcription_target is None:
            return frozenset({self.generation_target})
        return frozenset({self.generation_target, self.transcription_target})


@dataclass(frozen=True)
class ValidationRequest:
    """Exactly one Target and no customer content."""

    target: Target

    def __post_init__(self) -> None:
        _require_instance(self.target, Target, "target")


@dataclass(frozen=True, eq=False)
class CredentialLease:
    """Admitted credential snapshot for one operation. Never serializable or copyable."""

    binding: Binding
    state: CredentialState
    secret: SecretValue = field(repr=False)
    permitted_targets: FrozenSet[Target]
    admission_id: str

    def __post_init__(self) -> None:
        _require_instance(self.binding, Binding, "binding")
        _require_instance(self.state, CredentialState, "state")
        _require_instance(self.secret, SecretValue, "secret")
        _require_target_set(self.permitted_targets, "permitted_targets")
        _require_identifier(self.admission_id, "admission_id")

    def __reduce_ex__(self, protocol: object) -> object:
        raise TypeError("CredentialLease cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("CredentialLease cannot be serialized")

    def __copy__(self) -> "CredentialLease":
        raise TypeError("CredentialLease cannot be copied")

    def __deepcopy__(self, memo: object) -> "CredentialLease":
        raise TypeError("CredentialLease cannot be copied")


def _require_count(value: object, name: str) -> None:
    if value is None:
        return
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative int or None")


def _reported_count(value: object) -> Optional[int]:
    return value if type(value) is int and value >= 0 else None


def _reported_seconds(value: object) -> Optional[float]:
    if type(value) not in (int, float):
        return None
    number = float(value)  # type: ignore[arg-type]
    return number if math.isfinite(number) and number >= 0 else None


@dataclass(frozen=True)
class UsageEntry:
    """Provider-reported usage for one attempted operation. Null means unavailable, not zero."""

    operation: Operation
    model: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    audio_seconds: Optional[float] = None
    provider_request_id: Optional[str] = None

    def __post_init__(self) -> None:
        _require_instance(self.operation, Operation, "operation")
        _require_identifier(self.model, "model")
        for name in ("input_tokens", "output_tokens", "total_tokens"):
            _require_count(getattr(self, name), name)
        if self.audio_seconds is not None:
            if type(self.audio_seconds) not in (int, float) or _reported_seconds(self.audio_seconds) is None:
                raise ValueError("audio_seconds must be a finite nonnegative number or None")
        if self.provider_request_id is not None:
            _require_identifier(self.provider_request_id, "provider_request_id")

    @classmethod
    def from_reported(
        cls,
        operation: Operation,
        model: str,
        *,
        input_tokens: object = None,
        output_tokens: object = None,
        total_tokens: object = None,
        audio_seconds: object = None,
        provider_request_id: object = None,
        secret: Optional[SecretValue] = None,
    ) -> "UsageEntry":
        """Copy only well-formed provider-reported values; malformed or negative become null.

        Nothing is derived: a missing total stays null even when parts are present.
        """
        return cls(
            operation=operation,
            model=model,
            input_tokens=_reported_count(input_tokens),
            output_tokens=_reported_count(output_tokens),
            total_tokens=_reported_count(total_tokens),
            audio_seconds=_reported_seconds(audio_seconds),
            provider_request_id=sanitize_provider_request_id(provider_request_id, secret),
        )


def _require_usage(value: object) -> None:
    if not isinstance(value, tuple) or not all(isinstance(item, UsageEntry) for item in value):
        raise TypeError("usage must be a tuple of UsageEntry")


_REJECTION_REASONS = frozenset({ErrorCode.CREDENTIAL_REJECTED, ErrorCode.CAPABILITY_DENIED})


def _require_validation_status(status: object, reason_code: object) -> None:
    # L6: only definitive provider rejections are "rejected"; anything inconclusive
    # is "indeterminate" with a reason, never reported as an invalid key.
    _require_instance(status, ValidationStatus, "status")
    if reason_code is not None:
        _require_instance(reason_code, ErrorCode, "reason_code")
    if status is ValidationStatus.VALID:
        if reason_code is not None:
            raise ValueError("valid results must not carry a reason_code")
    elif status is ValidationStatus.REJECTED:
        if reason_code not in _REJECTION_REASONS:
            raise ValueError("rejected results require a definitive rejection reason_code")
    elif reason_code is None or reason_code in _REJECTION_REASONS:
        raise ValueError("indeterminate results require a non-rejection reason_code")


@dataclass(frozen=True)
class InvocationResult:
    """Outcome of a verified invocation. Result content is excluded from repr."""

    request_id: str
    provider: str
    model: str
    file_type: FileType
    outcome: Outcome
    result: Optional[str] = field(default=None, repr=False)
    error_code: Optional[ErrorCode] = None
    usage: Tuple[UsageEntry, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.request_id, "request_id")
        _require_identifier(self.provider, "provider")
        _require_identifier(self.model, "model")
        _require_instance(self.file_type, FileType, "file_type")
        _require_instance(self.outcome, Outcome, "outcome")
        if self.outcome is Outcome.SUCCESS:
            if not isinstance(self.result, str) or not self.result.strip():
                raise ValueError("success requires a nonempty result")
            if self.error_code is not None:
                raise ValueError("success must not carry an error_code")
        else:
            if self.result is not None:
                raise ValueError("error results must have a null result")
            _require_instance(self.error_code, ErrorCode, "error_code")
        _require_usage(self.usage)


@dataclass(frozen=True)
class ValidationResult:
    """Version-bound validation outcome. The Binding is internal; no provider response text."""

    request_id: str
    binding: Binding
    target: Target
    checked_at: datetime
    status: ValidationStatus
    reason_code: Optional[ErrorCode] = None
    usage: Tuple[UsageEntry, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.request_id, "request_id")
        _require_instance(self.binding, Binding, "binding")
        _require_instance(self.target, Target, "target")
        _require_utc(self.checked_at, "checked_at")
        _require_validation_status(self.status, self.reason_code)
        _require_usage(self.usage)


_BOUNDARY_CODES = frozenset({ErrorCode.INVALID_INPUT, ErrorCode.ACCESS_DENIED})


@dataclass(frozen=True)
class BoundaryFailure:
    """Failure before verification completes. Reflects no unverified scope/provider/model."""

    request_id: str
    error_code: ErrorCode
    outcome: Outcome = field(default=Outcome.ERROR, init=False)
    result: None = field(default=None, init=False)
    usage: Tuple[UsageEntry, ...] = field(default=(), init=False)

    def __post_init__(self) -> None:
        try:
            canonical = str(uuid.UUID(self.request_id))
        except (TypeError, ValueError, AttributeError):
            raise ValueError("request_id must be a locally generated UUID") from None
        if canonical != self.request_id:
            raise ValueError("request_id must be a locally generated UUID")
        _require_instance(self.error_code, ErrorCode, "error_code")
        if self.error_code not in _BOUNDARY_CODES:
            raise ValueError("boundary failures use INVALID_INPUT or ACCESS_DENIED only")

    @classmethod
    def create(cls, error_code: ErrorCode) -> "BoundaryFailure":
        return cls(request_id=new_request_id(), error_code=error_code)


@dataclass(frozen=True)
class StepOutput:
    """Result of one ProviderSession generation or transcription step.

    Transcription text may be empty (no speech); the orchestrator decides how an
    empty generation is handled (PROVIDER_RESPONSE_INVALID per L2).
    """

    text: str = field(repr=False)
    usage: UsageEntry

    def __post_init__(self) -> None:
        _require_instance(self.text, str, "text")
        _require_instance(self.usage, UsageEntry, "usage")


@dataclass(frozen=True)
class ProbeOutcome:
    """Result of one ProviderSession validation probe; the orchestrator adds binding/time."""

    status: ValidationStatus
    reason_code: Optional[ErrorCode]
    usage: UsageEntry

    def __post_init__(self) -> None:
        _require_validation_status(self.status, self.reason_code)
        _require_instance(self.usage, UsageEntry, "usage")
