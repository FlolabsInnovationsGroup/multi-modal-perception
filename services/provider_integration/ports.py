"""Injected boundary protocols (L2).

verify, invoke, validate and session operations are async. ``admit`` and
``open_session`` are factories returning async context managers used with
``async with``. Capability lookup is synchronous. Implementations report
failures by raising ProviderIntegrationError (or ProviderOperationError from a
session) with an allowlisted code; they never return, log or embed secrets.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import FrozenSet, Protocol, runtime_checkable

from services.provider_integration.config import ProviderConfig
from services.provider_integration.types import (
    AudioFormat,
    Binding,
    ContextKind,
    CredentialLease,
    ProbeOutcome,
    StepOutput,
    Target,
    VerifiedContext,
)


@runtime_checkable
class ContextVerifier(Protocol):
    async def verify(
        self,
        call_evidence: object,
        requested_binding: Binding,
        kind: ContextKind,
        targets: FrozenSet[Target],
    ) -> VerifiedContext:
        """Authenticate the caller and return the bound context, or raise ACCESS_DENIED.

        ``call_evidence`` is opaque: only the verifier interprets it. Unknown,
        expired or mismatched evidence must be denied before any credential access.
        """
        ...


@runtime_checkable
class CredentialReader(Protocol):
    def admit(
        self, context: VerifiedContext, targets: FrozenSet[Target]
    ) -> AbstractAsyncContextManager[CredentialLease]:
        """Admit exactly the bound scope/ref/version/state for one operation.

        Must never search for, enumerate or substitute another version, source or
        credential. Release the admission on every exit. Outage raises
        CREDENTIAL_UNAVAILABLE; a binding mismatch raises ACCESS_DENIED.
        """
        ...


@runtime_checkable
class ProviderSession(Protocol):
    async def generate_text(
        self, target: Target, text: str, remaining_seconds: float
    ) -> StepOutput:
        ...

    async def transcribe_audio(
        self,
        target: Target,
        audio: bytes,
        audio_format: AudioFormat,
        remaining_seconds: float,
    ) -> StepOutput:
        ...

    async def validate_access(self, target: Target, remaining_seconds: float) -> ProbeOutcome:
        """Run exactly one fixed synthetic probe for ``target``; no customer content."""
        ...


@runtime_checkable
class ProviderAdapter(Protocol):
    def supported_operations(self) -> FrozenSet[Target]:
        """Immutable configured operation/model pairs this adapter implements."""
        ...

    def open_session(
        self, lease: CredentialLease, config: ProviderConfig
    ) -> AbstractAsyncContextManager[ProviderSession]:
        """Open one request-local session for this lease; close it on every exit.

        Sessions use only ``config.destination`` and never activate, update or
        delete a credential.
        """
        ...
