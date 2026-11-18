"""Live settings for the backend connection and the approved provider targets (T5).

Built from an explicit mapping (the route layer passes the process environment).
Every value is required: a missing or invalid value returns ``None`` and the
routes refuse requests with NOT_CONFIGURED instead of guessing a default. The
error never echoes a value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Mapping, Optional
from urllib.parse import urlsplit

from services.provider_integration.config import GenerationSettings, ProviderConfig
from services.provider_integration.types import Operation, SecretValue, Target

# Environment variable names (documented in the technical design and README).
ENV_BACKEND_URL = "FLOBRAIN_BACKEND_URL"
ENV_SERVICE_SECRET = "MULTIMODAL_SERVICE_SECRET"
ENV_TOKEN_ISSUER = "CREDENTIAL_JWT_ISSUER"
ENV_TOKEN_AUDIENCE = "CREDENTIAL_JWT_AUDIENCE"
ENV_APPROVED_TARGETS = "PROVIDER_APPROVED_TARGETS"

OPENAI_PROVIDER = "openai"
OPENAI_DESTINATION = "https://api.openai.com/v1/"
JWKS_PATH = "/internal/jwks/"
RESOLVE_PATH = "/internal/credentials/resolve"
MIN_SERVICE_SECRET_LENGTH = 32
MAX_CLAIM_TEXT = 256


@dataclass(frozen=True)
class LiveSettings:
    """Agreed backend contract values (P-1, backend response 2026-11-15)."""

    backend_base_url: str
    service_secret: SecretValue = field(repr=False)
    token_issuer: str
    token_audience: str
    approved_targets: FrozenSet[Target]
    jwks_path: str = JWKS_PATH
    resolve_path: str = RESOLVE_PATH
    max_token_lifetime_seconds: int = 90
    clock_skew_seconds: int = 30
    backend_timeout_seconds: float = 4.0
    jwks_cache_seconds: float = 300.0
    jwks_refresh_min_interval_seconds: float = 10.0
    jwks_max_age_seconds: float = 600.0  # keys unusable after 10 min without a successful fetch
    max_backend_response_bytes: int = 65_536
    max_token_bytes: int = 8_192
    replay_cache_size: int = 100_000

    def url(self, path: str) -> str:
        return self.backend_base_url + path


def _https_origin(value: object) -> Optional[str]:
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        return None
    return f"https://{parts.netloc}"


def _claim_text(value: object) -> Optional[str]:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > MAX_CLAIM_TEXT
        or not value.isascii()
    ):
        return None
    return value


def parse_targets(value: object) -> Optional[FrozenSet[Target]]:
    """Parse ``operation:model`` pairs separated by commas, for example
    ``generate_text:gpt-4o-mini,transcribe_audio:gpt-4o-mini-transcribe``."""
    if not isinstance(value, str) or not value.strip():
        return None
    targets = set()
    for item in value.split(","):
        operation, separator, model = item.strip().partition(":")
        if not separator:
            return None
        try:
            targets.add(Target(Operation(operation), model))
        except (TypeError, ValueError):
            return None
    return frozenset(targets)


def load_live_settings(env: Mapping[str, str]) -> Optional[LiveSettings]:
    """Return settings only when every required value is present and valid."""
    origin = _https_origin(env.get(ENV_BACKEND_URL))
    secret_text = env.get(ENV_SERVICE_SECRET)
    issuer = _claim_text(env.get(ENV_TOKEN_ISSUER))
    audience = _claim_text(env.get(ENV_TOKEN_AUDIENCE))
    targets = parse_targets(env.get(ENV_APPROVED_TARGETS))
    if (
        origin is None
        or issuer is None
        or audience is None
        or targets is None
        or not isinstance(secret_text, str)
        or len(secret_text) < MIN_SERVICE_SECRET_LENGTH
        or secret_text != secret_text.strip()
        or not secret_text.isascii()
    ):
        return None
    return LiveSettings(
        backend_base_url=origin,
        service_secret=SecretValue(secret_text),
        token_issuer=issuer,
        token_audience=audience,
        approved_targets=targets,
    )


def openai_provider_config(settings: LiveSettings, system_prompt: str) -> ProviderConfig:
    """The approved OpenAI configuration (L6 settings, D-5 approved targets)."""
    return ProviderConfig(
        provider=OPENAI_PROVIDER,
        destination=OPENAI_DESTINATION,
        targets=settings.approved_targets,
        generation=GenerationSettings(max_tokens=256, temperature=0.4, system_prompt=system_prompt),
    )
