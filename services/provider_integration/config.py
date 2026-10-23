"""Explicit immutable limit and provider configuration (L5, L6 shape).

Configuration is injected at composition; requests never override it and
missing or invalid values are rejected rather than defaulted. Provider entries
are data only: this module contains no provider-specific values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from types import MappingProxyType
from typing import FrozenSet, Mapping, Optional
from urllib.parse import urlsplit

from services.provider_integration.types import (
    Operation,
    Target,
    _require_identifier,
    _require_instance,
    _require_target_set,
)


def _reject_unknown_or_missing(data: object, allowed: FrozenSet[str], name: str) -> None:
    if not isinstance(data, Mapping):
        raise TypeError(f"{name} must be a mapping")
    keys = set(data)
    if keys - allowed:
        raise ValueError(f"{name} contains unknown fields")
    if allowed - keys:
        raise ValueError(f"{name} is missing required fields")


def _require_positive_int(value: object, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive int")


def _require_positive_seconds(value: object, name: str) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:  # type: ignore[arg-type]
        raise ValueError(f"{name} must be a positive finite number")


_BYTE_LIMITS = (
    "max_text_bytes",
    "max_prompt_bytes",
    "max_transcript_bytes",
    "max_audio_bytes",
    "max_generation_bytes",
    "max_response_body_bytes",
)
_TIMEOUTS = (
    "invocation_timeout_seconds",
    "validation_timeout_seconds",
    "verify_timeout_seconds",
    "admit_timeout_seconds",
    "generation_call_timeout_seconds",
    "transcription_call_timeout_seconds",
    "validation_call_timeout_seconds",
    "connect_timeout_seconds",
    "cleanup_timeout_seconds",
)


@dataclass(frozen=True)
class LimitProfile:
    """Local operating profile. These are engineering limits, not provider quotas or SLOs."""

    max_text_bytes: int
    max_prompt_bytes: int
    max_transcript_bytes: int
    max_audio_bytes: int
    max_generation_bytes: int
    max_response_body_bytes: int
    invocation_timeout_seconds: float
    validation_timeout_seconds: float
    verify_timeout_seconds: float
    admit_timeout_seconds: float
    generation_call_timeout_seconds: float
    transcription_call_timeout_seconds: float
    validation_call_timeout_seconds: float
    connect_timeout_seconds: float
    cleanup_timeout_seconds: float
    max_concurrent_operations: int
    max_retries: int
    follow_redirects: bool

    def __post_init__(self) -> None:
        for name in _BYTE_LIMITS + ("max_concurrent_operations",):
            _require_positive_int(getattr(self, name), name)
        for name in _TIMEOUTS:
            _require_positive_seconds(getattr(self, name), name)
        if type(self.max_retries) is not int or self.max_retries != 0:
            raise ValueError("max_retries must be 0")
        if self.follow_redirects is not False:
            raise ValueError("follow_redirects must be False")
        overall = min(self.invocation_timeout_seconds, self.validation_timeout_seconds)
        if self.verify_timeout_seconds > overall or self.admit_timeout_seconds > overall:
            raise ValueError("verify/admit timeouts must not exceed the overall deadlines")
        if (
            self.generation_call_timeout_seconds > self.invocation_timeout_seconds
            or self.transcription_call_timeout_seconds > self.invocation_timeout_seconds
        ):
            raise ValueError("invocation call timeouts must not exceed the invocation deadline")
        if self.validation_call_timeout_seconds > self.validation_timeout_seconds:
            raise ValueError("validation call timeout must not exceed the validation deadline")
        shortest_call = min(
            self.generation_call_timeout_seconds,
            self.transcription_call_timeout_seconds,
            self.validation_call_timeout_seconds,
        )
        if self.connect_timeout_seconds > shortest_call:
            raise ValueError("connect timeout must not exceed any call timeout")

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "LimitProfile":
        allowed = frozenset(f.name for f in fields(cls))
        _reject_unknown_or_missing(data, allowed, "limit profile")
        return cls(**data)  # type: ignore[arg-type]


# T1-accepted local M1 profile (L5, accepted 2026-10-23). Not a production quota.
LOCAL_LIMIT_PROFILE = LimitProfile(
    max_text_bytes=65_536,
    max_prompt_bytes=131_072,
    max_transcript_bytes=131_072,
    max_audio_bytes=10_485_760,
    max_generation_bytes=65_536,
    max_response_body_bytes=1_048_576,
    invocation_timeout_seconds=90,
    validation_timeout_seconds=20,
    verify_timeout_seconds=5,
    admit_timeout_seconds=5,
    generation_call_timeout_seconds=30,
    transcription_call_timeout_seconds=60,
    validation_call_timeout_seconds=15,
    connect_timeout_seconds=5,
    cleanup_timeout_seconds=2,
    max_concurrent_operations=8,
    max_retries=0,
    follow_redirects=False,
)


@dataclass(frozen=True)
class GenerationSettings:
    max_tokens: int
    temperature: float
    system_prompt: str

    def __post_init__(self) -> None:
        _require_positive_int(self.max_tokens, "max_tokens")
        if (
            type(self.temperature) not in (int, float)
            or not math.isfinite(self.temperature)
            or self.temperature < 0
        ):
            raise ValueError("temperature must be a finite nonnegative number")
        if not isinstance(self.system_prompt, str) or not self.system_prompt.strip():
            raise ValueError("system_prompt must be a nonempty string")

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "GenerationSettings":
        allowed = frozenset(f.name for f in fields(cls))
        _reject_unknown_or_missing(data, allowed, "generation settings")
        return cls(**data)  # type: ignore[arg-type]


def _require_destination(value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("destination must be an https URL")
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
    ):
        raise ValueError("destination must be an https URL without credentials, query or fragment")


@dataclass(frozen=True)
class ProviderConfig:
    """One supported provider: approved destination, exact targets and generation settings."""

    provider: str
    destination: str
    targets: FrozenSet[Target]
    generation: GenerationSettings

    def __post_init__(self) -> None:
        _require_identifier(self.provider, "provider")
        _require_destination(self.destination)
        _require_target_set(self.targets, "targets")
        _require_instance(self.generation, GenerationSettings, "generation")

    def supports(self, target: Target) -> bool:
        return isinstance(target, Target) and target in self.targets

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "ProviderConfig":
        _reject_unknown_or_missing(
            data, frozenset({"provider", "destination", "targets", "generation"}), "provider config"
        )
        raw_targets = data["targets"]
        if isinstance(raw_targets, (str, bytes, Mapping)) or not hasattr(raw_targets, "__iter__"):
            raise TypeError("targets must be a sequence of mappings")
        targets = []
        for item in raw_targets:  # type: ignore[union-attr]
            _reject_unknown_or_missing(item, frozenset({"operation", "model"}), "target")
            try:
                operation = Operation(item["operation"])
            except ValueError:
                raise ValueError("target operation is not supported") from None
            targets.append(Target(operation=operation, model=item["model"]))
        return cls(
            provider=data["provider"],  # type: ignore[arg-type]
            destination=data["destination"],  # type: ignore[arg-type]
            targets=frozenset(targets),
            generation=GenerationSettings.from_mapping(data["generation"]),  # type: ignore[arg-type]
        )


@dataclass(frozen=True, eq=False)
class ModuleConfig:
    """Composition-time configuration. An empty provider map means nothing is enabled."""

    limits: LimitProfile
    providers: Mapping[str, ProviderConfig]

    def __post_init__(self) -> None:
        _require_instance(self.limits, LimitProfile, "limits")
        if not isinstance(self.providers, Mapping):
            raise TypeError("providers must be a mapping")
        copied = dict(self.providers)
        for key, value in copied.items():
            _require_instance(value, ProviderConfig, "provider config")
            if key != value.provider:
                raise ValueError("provider keys must match their configuration")
        object.__setattr__(self, "providers", MappingProxyType(copied))

    def provider_config(self, provider: str) -> Optional[ProviderConfig]:
        return self.providers.get(provider) if isinstance(provider, str) else None

    def supports(self, provider: str, target: Target) -> bool:
        config = self.provider_config(provider)
        return config is not None and config.supports(target)
