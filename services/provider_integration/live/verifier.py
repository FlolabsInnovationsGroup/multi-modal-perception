"""Live ContextVerifier: checks the backend's signed request token (T5.2).

Contract (P-1; backend response 2026-11-15): ES256 JWT with ``iss``, ``aud``,
``iat``, ``nbf``, ``exp``, ``jti``, ``kind``, a five-field ``binding`` and
``targets``. Lifetime at most 90 s, clock skew 30 s. Public keys come from the
backend's protected JWKS endpoint and are cached; an unknown ``kid`` triggers
one re-fetch (rate-limited), which also covers a signing-key switch (C-1).

Every failure raises ACCESS_DENIED with nothing reflected. Only ES256 is
accepted, so ``none`` and HS256 tokens are refused. A ``jti`` is accepted once
per process for verification; the backend's credential endpoint enforces single
use across instances.
"""

from __future__ import annotations

import asyncio
import math
import time
from datetime import datetime, timezone
from typing import Callable, Dict, FrozenSet, Mapping, Optional

import httpx
import jwt

from services.provider_integration.errors import ErrorCode, ProviderIntegrationError
from services.provider_integration.live._http import BackendCallError, call_backend
from services.provider_integration.live.config import LiveSettings
from services.provider_integration.types import (
    Binding,
    ContextKind,
    CredentialSource,
    Operation,
    SecretValue,
    Target,
    VerifiedContext,
    is_valid_identifier,
)

ALGORITHM = "ES256"
_BINDING_FIELDS = frozenset({"scope_id", "credential_ref", "credential_version", "credential_source", "provider"})
_TARGET_FIELDS = frozenset({"operation", "model"})
_REQUIRED_CLAIMS = ["iss", "aud", "iat", "nbf", "exp", "jti"]


def _deny() -> ProviderIntegrationError:
    return ProviderIntegrationError(ErrorCode.ACCESS_DENIED)


def _number(value: object) -> Optional[float]:
    """A finite numeric time claim; NaN, infinity and booleans are refused (review fix 1)."""
    if type(value) in (int, float) and math.isfinite(value):  # type: ignore[arg-type]
        return float(value)  # type: ignore[arg-type]
    return None


def parse_binding_claim(value: object) -> Binding:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise _deny()
    source = value["credential_source"]
    if type(source) is not str:
        raise _deny()
    try:
        return Binding(
            scope_id=value["scope_id"],
            credential_ref=value["credential_ref"],
            credential_version=value["credential_version"],
            credential_source=CredentialSource(source),
            provider=value["provider"],
        )
    except (TypeError, ValueError):
        raise _deny() from None


def parse_targets_claim(value: object) -> FrozenSet[Target]:
    if not isinstance(value, list) or not value or len(value) > 16:
        raise _deny()
    targets = set()
    for item in value:
        if not isinstance(item, Mapping) or set(item) != _TARGET_FIELDS or type(item["operation"]) is not str:
            raise _deny()
        try:
            targets.add(Target(Operation(item["operation"]), item["model"]))
        except (TypeError, ValueError):
            raise _deny() from None
    return frozenset(targets)


class JwksClient:
    """Fetches and caches the backend's ES256 public keys by ``kid``."""

    def __init__(
        self,
        settings: LiveSettings,
        *,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._clock = clock
        self._keys: Dict[str, object] = {}
        self._succeeded_at: Optional[float] = None  # last successful fetch
        self._attempted_at: Optional[float] = None  # last attempt, successful or not (rate limit)
        self._lock: Optional[asyncio.Lock] = None
        self.fetches = 0

    def _age(self) -> Optional[float]:
        return None if self._succeeded_at is None else self._clock() - self._succeeded_at

    def _fresh(self) -> bool:
        age = self._age()
        return age is not None and age < self._settings.jwks_cache_seconds

    def _may_refresh(self) -> bool:
        return (
            self._attempted_at is None
            or self._clock() - self._attempted_at >= self._settings.jwks_refresh_min_interval_seconds
        )

    async def key_for(self, kid: str) -> object:
        if self._fresh() and kid in self._keys:
            return self._keys[kid]
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            if not (self._fresh() and kid in self._keys) and self._may_refresh():
                await self._refresh()
        age = self._age()
        if age is None or age > self._settings.jwks_max_age_seconds:
            self._keys = {}  # review fix 5: never verify with keys older than the hard limit
            raise _deny()
        key = self._keys.get(kid)
        if key is None:
            raise _deny()
        return key

    async def _refresh(self) -> None:
        """Replace the key set on success; on failure keep the last good set (until the hard limit)."""
        self._attempted_at = self._clock()
        self.fetches += 1
        try:
            status, document = await call_backend(
                self._settings, "GET", self._settings.jwks_path,
                timeout_seconds=self._settings.backend_timeout_seconds, transport=self._transport,
            )
        except BackendCallError:
            return
        keys = _parse_jwks(document) if status == 200 else None
        if keys is None:
            return
        self._keys = keys
        self._succeeded_at = self._attempted_at


def _parse_jwks(document: object) -> Optional[Dict[str, object]]:
    """Usable ES256 public keys by kid, or None for a document that must not be trusted."""
    if not isinstance(document, Mapping) or not isinstance(document.get("keys"), list):
        return None
    kids = [entry.get("kid") for entry in document["keys"] if isinstance(entry, Mapping)]
    if len(kids) != len(set(map(str, kids))):
        return None  # review fix 6: duplicate kids make the key choice ambiguous
    keys: Dict[str, object] = {}
    for entry in document["keys"]:
        if (
            not isinstance(entry, Mapping)
            or entry.get("kty") != "EC"
            or entry.get("crv") != "P-256"
            or entry.get("alg", ALGORITHM) != ALGORITHM
            or entry.get("use", "sig") != "sig"  # review fix 6: signing keys only
            or "d" in entry  # never accept private key material
            or not is_valid_identifier(entry.get("kid"))
        ):
            continue
        try:
            keys[entry["kid"]] = jwt.PyJWK(dict(entry), algorithm=ALGORITHM).key
        except Exception:
            continue
    return keys


class JwtContextVerifier:
    """ContextVerifier for the backend's ES256 request tokens."""

    def __init__(
        self,
        settings: LiveSettings,
        *,
        jwks: Optional[JwksClient] = None,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self._settings = settings
        self._jwks = jwks if jwks is not None else JwksClient(settings)
        self._now = wall_clock
        self._seen: Dict[str, float] = {}

    async def inspect(self, token: object) -> Mapping[str, object]:
        """Fully verify the signature and time claims; return the claims. No replay mark."""
        settings = self._settings
        if type(token) is not str or not token or len(token) > settings.max_token_bytes or not token.isascii():
            raise _deny()
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise _deny() from None
        kid = header.get("kid")
        if header.get("alg") != ALGORITHM or not is_valid_identifier(kid):
            raise _deny()
        key = await self._jwks.key_for(kid)
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=[ALGORITHM],
                audience=settings.token_audience,
                issuer=settings.token_issuer,
                options={"require": _REQUIRED_CLAIMS, "verify_exp": False, "verify_nbf": False, "verify_iat": False},
            )
        except jwt.PyJWTError:
            raise _deny() from None
        now = self._now()
        skew = settings.clock_skew_seconds
        iat, nbf, exp = _number(claims.get("iat")), _number(claims.get("nbf")), _number(claims.get("exp"))
        if (
            iat is None or nbf is None or exp is None
            or exp <= iat
            or nbf > exp
            or exp - iat > settings.max_token_lifetime_seconds
            or now >= exp + skew
            or now + skew < nbf
            or now + skew < iat
            or not is_valid_identifier(claims.get("jti"))
        ):
            raise _deny()
        return claims

    def is_usable(self, claims: Mapping[str, object], kind: ContextKind) -> bool:
        """Route-level check before any body is read (review fix 2): the verified token is for
        this kind of route and its ``jti`` has not been used here. Does not consume the token;
        the handler's ``verify`` does."""
        return claims.get("kind") == kind.value and claims.get("jti") not in self._seen

    async def verify(
        self,
        call_evidence: object,
        requested_binding: Binding,
        kind: ContextKind,
        targets: FrozenSet[Target],
    ) -> VerifiedContext:
        claims = await self.inspect(call_evidence)
        if claims.get("kind") != kind.value:
            raise _deny()
        binding = parse_binding_claim(claims.get("binding"))
        if binding != requested_binding:
            raise _deny()
        allowed = parse_targets_claim(claims.get("targets"))
        if kind is ContextKind.VALIDATE and len(allowed) != 1:
            raise _deny()
        if not isinstance(targets, frozenset) or not targets or not targets <= allowed:
            raise _deny()
        jti = claims["jti"]
        exp = float(claims["exp"])  # type: ignore[arg-type]
        self._mark_used(jti, exp)  # type: ignore[arg-type]
        return VerifiedContext(
            binding=binding,
            request_id=jti,  # type: ignore[arg-type]
            kind=kind,
            allowed_targets=allowed,
            expires_at=datetime.fromtimestamp(exp, tz=timezone.utc),
            credential_token=SecretValue(call_evidence),  # type: ignore[arg-type]
        )

    def _mark_used(self, jti: str, exp: float) -> None:
        now = self._now()
        horizon = now - self._settings.clock_skew_seconds
        if len(self._seen) >= self._settings.replay_cache_size:
            self._seen = {key: value for key, value in self._seen.items() if value > horizon}
        if jti in self._seen or len(self._seen) >= self._settings.replay_cache_size:
            raise _deny()
        self._seen[jti] = exp
