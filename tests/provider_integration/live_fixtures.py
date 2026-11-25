"""Shared offline fixtures for the live connector tests (T5).

Synthetic ES256 key pairs are generated in memory per test run; the backend's
JWKS and credential endpoints are simulated with httpx.MockTransport. Nothing
here touches the network or real credentials.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Callable, Dict, List, Optional

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

from services.provider_integration.live.config import load_live_settings

BACKEND = "https://backend.example.test"
SERVICE_SECRET = "test-service-secret-redacted-0123456789abcdef"
ISSUER = "flobrain-backend"
AUDIENCE = "multimodal-perception"
TARGETS_ENV = "generate_text:gpt-4o-mini,transcribe_audio:gpt-4o-mini-transcribe"
PROVIDER_KEY = "test-provider-key-live-scope-a-v1"
NOW = 1_800_000_000.0

ENV = {
    "FLOBRAIN_BACKEND_URL": BACKEND,
    "MULTIMODAL_SERVICE_SECRET": SERVICE_SECRET,
    "CREDENTIAL_JWT_ISSUER": ISSUER,
    "CREDENTIAL_JWT_AUDIENCE": AUDIENCE,
    "PROVIDER_APPROVED_TARGETS": TARGETS_ENV,
}

# Ofon's confirmed format (C-4, 2026-11-22): UUID scope and reference, numeric version.
SCOPE_A = "2f1c6c1e-6b1f-4a6e-9d1a-3f0f2b7c9a11"
SCOPE_B = "7a9e3c55-0d2b-4c8f-a1e6-5b4d3c2a1f00"
REF_A = "8d7e2b4a-1c3f-4e5d-9a8b-7c6d5e4f3a2b"
REF_B = "c4b3a2f1-9e8d-4c7b-8a6f-5e4d3c2b1a09"
BINDING = {
    "scope_id": SCOPE_A,
    "credential_ref": REF_A,
    "credential_version": 1,
    "credential_source": "customer",
    "provider": "openai",
}
GENERATE = {"operation": "generate_text", "model": "gpt-4o-mini"}
TRANSCRIBE = {"operation": "transcribe_audio", "model": "gpt-4o-mini-transcribe"}


def settings(**overrides):
    env = dict(ENV)
    env.update(overrides)
    return load_live_settings(env)


class SigningKey:
    def __init__(self, kid: str = "key-1") -> None:
        self.kid = kid
        self.private = ec.generate_private_key(ec.SECP256R1())

    def jwk(self) -> dict:
        data = ECAlgorithm.to_jwk(self.private.public_key(), as_dict=True)
        data.update({"kid": self.kid, "alg": "ES256", "use": "sig"})
        return data

    def token(self, now: float = NOW, *, headers: Optional[dict] = None, **claim_overrides) -> str:
        claims = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": int(now),
            "nbf": int(now),
            "exp": int(now) + 90,
            "jti": str(uuid.uuid4()),
            "kind": "invoke",
            "binding": dict(BINDING),
            "targets": [dict(GENERATE), dict(TRANSCRIBE)],
        }
        for name, value in claim_overrides.items():
            if value is DROP:
                claims.pop(name, None)
            else:
                claims[name] = value
        return jwt.encode(claims, self.private, algorithm="ES256", headers={"kid": self.kid, **(headers or {})})


DROP = object()


class FakeBackend:
    """Simulated JWKS and credential endpoints with request capture."""

    def __init__(self, keys: List[SigningKey]) -> None:
        self.keys = keys
        self.requests: List[httpx.Request] = []
        self.jwks_status = 200
        self.jwks_override: Optional[object] = None
        self.resolve_status = 200
        self.resolve_body: Optional[object] = None
        self.resolve_raw: Optional[bytes] = None
        self.resolve_headers: Dict[str, str] = {}
        self.resolve_hook: Optional[Callable[[httpx.Request], None]] = None
        self.raise_error: Optional[BaseException] = None

    def resolve_ok(self, *, state: str = "active", binding: Optional[dict] = None, targets=None, key: str = PROVIDER_KEY):
        self.resolve_status = 200
        self.resolve_body = {
            "binding": dict(binding or BINDING),
            "state": state,
            "permitted_targets": targets if targets is not None else [dict(GENERATE), dict(TRANSCRIBE)],
            "key": key,
        }

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raise_error is not None:
            raise self.raise_error
        if request.url.path == "/internal/jwks/":
            body = self.jwks_override if self.jwks_override is not None else {"keys": [k.jwk() for k in self.keys]}
            return httpx.Response(self.jwks_status, json=body)
        if request.url.path == "/internal/credentials/resolve":
            if self.resolve_hook is not None:
                self.resolve_hook(request)
            if self.resolve_raw is not None:
                return httpx.Response(self.resolve_status, content=self.resolve_raw, headers=self.resolve_headers)
            return httpx.Response(self.resolve_status, json=self.resolve_body, headers=self.resolve_headers)
        return httpx.Response(404, json={"error": "not found"})

    def jwks_requests(self) -> List[httpx.Request]:
        return [r for r in self.requests if r.url.path == "/internal/jwks/"]

    def resolve_requests(self) -> List[httpx.Request]:
        return [r for r in self.requests if r.url.path == "/internal/credentials/resolve"]


class Clock:
    def __init__(self, start: float = 0.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value


def body_json(request: httpx.Request) -> dict:
    return json.loads(request.content.decode("utf-8"))


def wall(now: float = NOW) -> Callable[[], float]:
    return lambda: now


def real_now() -> float:
    return time.time()
