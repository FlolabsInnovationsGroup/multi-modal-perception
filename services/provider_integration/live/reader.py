"""Live CredentialReader: fetches one key version from the backend (T5.3).

Contract (P-1 section 4; backend response 2026-11-15): POST
``/internal/credentials/resolve`` with ``{"context_token": <verified token>}`` and
the service secret. A 200 reply is ``{"binding", "state", "permitted_targets",
"key"}``; the exact shape is still to be confirmed by the backend (C-4), so any
other shape is refused rather than guessed.

Mapping: 401/403 -> ACCESS_DENIED; any other non-200 status, a timeout or an
unreachable backend -> CREDENTIAL_UNAVAILABLE; a malformed or oversized reply ->
CREDENTIAL_UNAVAILABLE; a binding that differs from the token -> ACCESS_DENIED.
No retry and no fallback key. Reply bodies are never logged.
"""

from __future__ import annotations

import contextlib
import uuid
from typing import AsyncIterator, FrozenSet, Mapping, Optional

import httpx

from services.provider_integration.errors import ErrorCode, ProviderIntegrationError
from services.provider_integration.live._http import BackendCallError, KIND_BLOCKED, call_backend
from services.provider_integration.live.config import LiveSettings
from services.provider_integration.live.verifier import parse_binding_claim, parse_targets_claim
from services.provider_integration.types import (
    CredentialLease,
    CredentialState,
    SecretValue,
    Target,
    VerifiedContext,
)

_REPLY_FIELDS = frozenset({"binding", "state", "permitted_targets", "key"})
_DENIED_STATUSES = frozenset({401, 403})
MAX_KEY_LENGTH = 1_024


def _fail(code: ErrorCode) -> ProviderIntegrationError:
    return ProviderIntegrationError(code)


class BackendCredentialReader:
    """CredentialReader that asks the backend for exactly the token's key version."""

    def __init__(self, settings: LiveSettings, *, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self._settings = settings
        self._transport = transport

    def admit(
        self, context: VerifiedContext, targets: FrozenSet[Target]
    ) -> contextlib.AbstractAsyncContextManager[CredentialLease]:
        return self._admission(context, targets)

    @contextlib.asynccontextmanager
    async def _admission(self, context: VerifiedContext, targets: FrozenSet[Target]) -> AsyncIterator[CredentialLease]:
        lease = await self._resolve(context, targets)
        yield lease

    async def _resolve(self, context: VerifiedContext, targets: FrozenSet[Target]) -> CredentialLease:
        if not isinstance(context, VerifiedContext) or context.credential_token is None:
            raise _fail(ErrorCode.ACCESS_DENIED)
        body = {"context_token": context.credential_token.reveal_for_session()}
        try:
            status, reply = await call_backend(
                self._settings, "POST", self._settings.resolve_path,
                json_body=body, timeout_seconds=self._settings.backend_timeout_seconds, transport=self._transport,
            )
        except BackendCallError as error:
            raise _fail(ErrorCode.INTERNAL_ERROR if error.kind == KIND_BLOCKED else ErrorCode.CREDENTIAL_UNAVAILABLE) from None
        finally:
            body.clear()
        if status in _DENIED_STATUSES:
            raise _fail(ErrorCode.ACCESS_DENIED)
        if status != 200:
            raise _fail(ErrorCode.CREDENTIAL_UNAVAILABLE)
        return self._lease_from(reply, context)

    def _lease_from(self, reply: object, context: VerifiedContext) -> CredentialLease:
        if not isinstance(reply, Mapping) or set(reply) != _REPLY_FIELDS:
            raise _fail(ErrorCode.CREDENTIAL_UNAVAILABLE)
        try:
            binding = parse_binding_claim(reply["binding"])
            permitted = parse_targets_claim(reply["permitted_targets"])
        except ProviderIntegrationError:
            raise _fail(ErrorCode.CREDENTIAL_UNAVAILABLE) from None
        if binding != context.binding:
            raise _fail(ErrorCode.ACCESS_DENIED)
        state_text = reply["state"]
        if type(state_text) is not str:
            raise _fail(ErrorCode.CREDENTIAL_UNAVAILABLE)
        try:
            state = CredentialState(state_text)
        except ValueError:
            raise _fail(ErrorCode.CREDENTIAL_UNAVAILABLE) from None
        key = reply["key"]
        if type(key) is not str or not key or len(key) > MAX_KEY_LENGTH or key != key.strip() or not key.isascii():
            raise _fail(ErrorCode.CREDENTIAL_UNAVAILABLE)
        return CredentialLease(
            binding=binding,
            state=state,
            secret=SecretValue(key),
            permitted_targets=permitted,
            admission_id=f"admission-{uuid.uuid4()}",
        )
