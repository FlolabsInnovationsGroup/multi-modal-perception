"""Explicit composition (T4.1; L1, L7). No globals, no environment, no test doubles.

``build_unconfigured`` returns a handler that denies every request before any
credential or provider access; it is the only default. ``build_handler``
composes the real orchestrator and adapters from explicitly supplied
dependencies. This is the only package module that refers to the adapters
package, and it imports the OpenAI adapter lazily so that importing wiring
does not load the provider SDK.

T4.1 decisions (approved 2026-10-23): C5 the package ``__init__`` does not
export the handler or wiring; C6 only these two builders exist, there is no
default live verifier/reader, and the adapter's test-only transport is never
set here (A5).
"""

from __future__ import annotations

import contextlib
from typing import AsyncIterator, FrozenSet, Mapping

from services.provider_integration.config import LOCAL_LIMIT_PROFILE, LimitProfile, ModuleConfig, ProviderConfig
from services.provider_integration.errors import ErrorCode, ProviderIntegrationError
from services.provider_integration.handler import Handler
from services.provider_integration.orchestrator import Orchestrator
from services.provider_integration.ports import ContextVerifier, CredentialReader
from services.provider_integration.types import Binding, ContextKind, CredentialLease, Target, VerifiedContext

OPENAI_PROVIDER = "openai"


class DenyAllVerifier:
    """Unconfigured default: no caller is ever verified."""

    async def verify(
        self,
        call_evidence: object,
        requested_binding: Binding,
        kind: ContextKind,
        targets: FrozenSet[Target],
    ) -> VerifiedContext:
        raise ProviderIntegrationError(ErrorCode.ACCESS_DENIED)


class DenyAllReader:
    """Unconfigured default: no credential is ever admitted."""

    def admit(
        self, context: VerifiedContext, targets: FrozenSet[Target]
    ) -> contextlib.AbstractAsyncContextManager[CredentialLease]:
        return self._deny()

    @contextlib.asynccontextmanager
    async def _deny(self) -> AsyncIterator[CredentialLease]:
        raise ProviderIntegrationError(ErrorCode.CREDENTIAL_UNAVAILABLE)
        yield  # pragma: no cover


def build_unconfigured(limits: LimitProfile = LOCAL_LIMIT_PROFILE) -> Handler:
    """A handler with deny-all verifier/reader and no enabled provider."""
    config = ModuleConfig(limits=limits, providers={})
    orchestrator = Orchestrator(config=config, reader=DenyAllReader(), adapters={})
    return Handler(verifier=DenyAllVerifier(), orchestrator=orchestrator, limits=limits)


def build_handler(
    *,
    verifier: ContextVerifier,
    reader: CredentialReader,
    providers: Mapping[str, ProviderConfig],
    limits: LimitProfile = LOCAL_LIMIT_PROFILE,
) -> Handler:
    """Compose a handler from explicit dependencies. Only OpenAI is supported in M1."""
    config = ModuleConfig(limits=limits, providers=providers)
    adapters = {}
    for name, provider_config in config.providers.items():
        if name != OPENAI_PROVIDER:
            raise ValueError("unsupported provider")
        from services.provider_integration.adapters.openai import OpenAIAdapter  # lazy: SDK only when composing

        adapters[name] = OpenAIAdapter(
            provider_config.targets,
            connect_timeout_seconds=limits.connect_timeout_seconds,
            max_response_bytes=limits.max_response_body_bytes,
        )
    orchestrator = Orchestrator(config=config, reader=reader, adapters=adapters)
    return Handler(verifier=verifier, orchestrator=orchestrator, limits=limits)
