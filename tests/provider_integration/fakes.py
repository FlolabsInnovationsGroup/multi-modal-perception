"""Test-only synthetic doubles for provider-integration tests (L3).

These live under tests/ only. Production code must never import them, and no
request field or environment setting can select them. They are not
authentication or storage implementations; they simulate the backend contract
so the core can be tested offline. Keys must be synthetic ``test-provider-key-``
placeholders.

Reader denial-code mapping (approved with T2.2, 2026-10-23; the real reader
should conform):

- missing record/version, disabled, deleted, expired, pending-for-invoke, or an
  old version after rotation -> CREDENTIAL_UNAVAILABLE
- provider or source mismatch, target not allowed by the context, expired or
  non-verified context -> ACCESS_DENIED
- target not permitted for the credential -> CAPABILITY_DENIED
- store outage -> CREDENTIAL_UNAVAILABLE

T2.3 adds a scripted ProviderAdapter double, a tampering reader and a raising
reader for orchestrator tests. They capture calls in test memory only.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import socket
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Dict, FrozenSet, List, Optional, Set, Tuple
from unittest import mock

from services.provider_integration import (
    LOCAL_LIMIT_PROFILE,
    AudioFormat,
    Binding,
    ContextKind,
    CredentialLease,
    CredentialSource,
    CredentialState,
    ErrorCode,
    GenerationSettings,
    InvocationInput,
    InvocationRequest,
    LimitProfile,
    ModuleConfig,
    Operation,
    ProbeOutcome,
    ProviderConfig,
    ProviderIntegrationError,
    SecretValue,
    StepOutput,
    Target,
    UsageEntry,
    ValidationRequest,
    ValidationResult,
    ValidationStatus,
    VerifiedContext,
    new_request_id,
)
from services.provider_integration.orchestrator import Orchestrator

SYNTHETIC_KEY_PREFIX = "test-provider-key-"
DEFAULT_START = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def _deny(code: ErrorCode) -> ProviderIntegrationError:
    return ProviderIntegrationError(code)


# --- network guard -----------------------------------------------------------

_LOOPBACK_NAMES = frozenset({"localhost"})


def _is_loopback(host: object) -> bool:
    if not isinstance(host, str):
        return False
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def network_guard_patchers() -> List["mock._patch"]:
    """Patchers that deny every non-loopback connection and DNS lookup.

    Loopback stays allowed because the asyncio event loop uses a local socket
    pair internally (notably on Windows); no test talks to a server.
    """
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo

    def _host(address: object) -> object:
        return address[0] if isinstance(address, tuple) and address else address

    def guarded_connect(self, address):  # type: ignore[no-untyped-def]
        if not _is_loopback(_host(address)):
            raise AssertionError("network access is not allowed in provider-integration tests")
        return original_connect(self, address)

    def guarded_connect_ex(self, address):  # type: ignore[no-untyped-def]
        if not _is_loopback(_host(address)):
            raise AssertionError("network access is not allowed in provider-integration tests")
        return original_connect_ex(self, address)

    def guarded_getaddrinfo(host, *args, **kwargs):  # type: ignore[no-untyped-def]
        if host is not None and not _is_loopback(host):
            raise AssertionError("DNS lookups are not allowed in provider-integration tests")
        return original_getaddrinfo(host, *args, **kwargs)

    return [
        mock.patch.object(socket.socket, "connect", guarded_connect),
        mock.patch.object(socket.socket, "connect_ex", guarded_connect_ex),
        mock.patch.object(socket, "getaddrinfo", guarded_getaddrinfo),
    ]


# --- clock and pause points -------------------------------------------------


class FakeClock:
    """Test-controlled UTC wall clock and monotonic clock."""

    def __init__(self, start: datetime = DEFAULT_START) -> None:
        self._now = start
        self._monotonic = 0.0

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)
        self._monotonic += seconds


class PauseGate:
    """Deterministic pause point: sets ``entered`` then waits for ``release``."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def pause(self) -> None:
        self.entered.set()
        await self.release.wait()


# --- verifier ---------------------------------------------------------------


class FakeContextVerifier:
    """Returns contexts prepared by explicit test registrations. Not authentication."""

    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock
        self._registrations: Dict[object, VerifiedContext] = {}
        self.calls = 0

    def register(self, evidence: object, context: VerifiedContext) -> None:
        if not isinstance(context, VerifiedContext):
            raise TypeError("context must be a VerifiedContext")
        self._registrations[evidence] = context

    def revoke(self, evidence: object) -> None:
        self._registrations.pop(evidence, None)

    async def verify(
        self,
        call_evidence: object,
        requested_binding: Binding,
        kind: ContextKind,
        targets: FrozenSet[Target],
    ) -> VerifiedContext:
        self.calls += 1
        try:
            context = self._registrations.get(call_evidence)
        except TypeError:  # unhashable evidence
            context = None
        if (
            context is None
            or context.is_expired(self._clock.now())
            or context.binding != requested_binding
            or context.kind is not kind
            or not isinstance(targets, frozenset)
            or not targets
            or not targets <= context.allowed_targets
        ):
            raise _deny(ErrorCode.ACCESS_DENIED) from None
        return context


# --- credential store (reader + simulated backend lifecycle) ----------------


@dataclass
class _Record:
    source: CredentialSource
    provider: str
    state: CredentialState
    plaintext: str = field(repr=False)
    targets: FrozenSet[Target]


_Key = Tuple[str, str, str]


class FakeCredentialStore:
    """Atomic in-memory CredentialReader with test-only lifecycle actions.

    One asyncio lock covers admission checks and every lifecycle change, so a
    request admitted before a change keeps its snapshot and a later admission
    sees the change. Each admission gets a new SecretValue (no caching).
    """

    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock
        self._lock = asyncio.Lock()
        self._records: Dict[_Key, _Record] = {}
        self._active: Dict[Tuple[str, str], str] = {}
        self._in_flight: Set[str] = set()
        self.outage = False
        self.admit_calls = 0
        self.admissions_total = 0
        self.admit_gate: Optional[PauseGate] = None
        self.lifecycle_gate: Optional[PauseGate] = None

    # -- observation helpers -------------------------------------------------

    @property
    def in_flight(self) -> int:
        return len(self._in_flight)

    @property
    def locked(self) -> bool:
        return self._lock.locked()

    def active_version(self, scope_id: str, credential_ref: str) -> Optional[str]:
        return self._active.get((scope_id, credential_ref))

    def state_of(self, scope_id: str, credential_ref: str, version: str) -> Optional[CredentialState]:
        record = self._records.get((scope_id, credential_ref, version))
        return record.state if record else None

    # -- synchronous setup -----------------------------------------------------

    def add_record(
        self,
        scope_id: str,
        credential_ref: str,
        version: str,
        *,
        key: str,
        state: CredentialState = CredentialState.ACTIVE,
        source: CredentialSource = CredentialSource.CUSTOMER,
        provider: str = "openai",
        targets: FrozenSet[Target],
        active: bool = False,
    ) -> None:
        """Register a synthetic record before concurrent work starts."""
        if not isinstance(key, str) or not key.startswith(SYNTHETIC_KEY_PREFIX):
            raise ValueError("fake credentials must use the synthetic test-provider-key- prefix")
        if not isinstance(state, CredentialState):
            raise TypeError("state must be a CredentialState")
        Binding(scope_id, credential_ref, version, source, provider)  # validates identifiers
        if not isinstance(targets, frozenset) or not targets or not all(isinstance(t, Target) for t in targets):
            raise TypeError("targets must be a nonempty frozenset of Target")
        if active and state is not CredentialState.ACTIVE:
            raise ValueError("only an active record can be the active version")
        self._records[(scope_id, credential_ref, version)] = _Record(source, provider, state, key, targets)
        if active:
            self._active[(scope_id, credential_ref)] = version

    # -- test-only lifecycle actions (same lock as admission) -----------------

    @contextlib.asynccontextmanager
    async def _lifecycle(self) -> AsyncIterator[None]:
        async with self._lock:
            if self.lifecycle_gate is not None:
                await self.lifecycle_gate.pause()
            yield

    async def add_pending(
        self,
        scope_id: str,
        credential_ref: str,
        version: str,
        *,
        key: str,
        targets: FrozenSet[Target],
        source: CredentialSource = CredentialSource.CUSTOMER,
        provider: str = "openai",
    ) -> None:
        async with self._lifecycle():
            if (scope_id, credential_ref, version) in self._records:
                raise ValueError("version already exists")
            self.add_record(
                scope_id, credential_ref, version, key=key, state=CredentialState.PENDING,
                source=source, provider=provider, targets=targets,
            )

    async def rotate(self, scope_id: str, credential_ref: str, new_version: str) -> None:
        """Activate a pending version; the previous active version becomes disabled."""
        async with self._lifecycle():
            record = self._records.get((scope_id, credential_ref, new_version))
            if record is None or record.state is not CredentialState.PENDING:
                raise ValueError("rotation requires an existing pending version")
            previous = self._active.get((scope_id, credential_ref))
            if previous is not None:
                self._records[(scope_id, credential_ref, previous)].state = CredentialState.DISABLED
            record.state = CredentialState.ACTIVE
            self._active[(scope_id, credential_ref)] = new_version

    async def disable(self, scope_id: str, credential_ref: str, version: str) -> None:
        await self._set_state(scope_id, credential_ref, version, CredentialState.DISABLED)

    async def delete(self, scope_id: str, credential_ref: str, version: str) -> None:
        await self._set_state(scope_id, credential_ref, version, CredentialState.DELETED)

    async def _set_state(
        self, scope_id: str, credential_ref: str, version: str, state: CredentialState
    ) -> None:
        async with self._lifecycle():
            record = self._records.get((scope_id, credential_ref, version))
            if record is None:
                raise ValueError("unknown record")
            record.state = state
            if self._active.get((scope_id, credential_ref)) == version:
                del self._active[(scope_id, credential_ref)]

    # -- simulated backend acceptance ------------------------------------------

    def backend_accepts(self, result: ValidationResult) -> bool:
        """Simulated backend: refuse a result whose exact version is gone or changed."""
        if not isinstance(result, ValidationResult):
            return False
        binding = result.binding
        record = self._records.get((binding.scope_id, binding.credential_ref, binding.credential_version))
        return (
            record is not None
            and record.state in (CredentialState.PENDING, CredentialState.ACTIVE)
            and record.provider == binding.provider
            and record.source is binding.credential_source
        )

    # -- CredentialReader --------------------------------------------------------

    def admit(
        self, context: VerifiedContext, targets: FrozenSet[Target]
    ) -> contextlib.AbstractAsyncContextManager[CredentialLease]:
        return self._admission(context, targets)

    @contextlib.asynccontextmanager
    async def _admission(
        self, context: VerifiedContext, targets: FrozenSet[Target]
    ) -> AsyncIterator[CredentialLease]:
        self.admit_calls += 1
        lease = await self._admit_locked(context, targets)
        try:
            yield lease
        finally:
            self._in_flight.discard(lease.admission_id)

    def _state_permits(self, record: _Record, binding: Binding, kind: ContextKind) -> bool:
        if kind is ContextKind.INVOKE:
            return (
                record.state is CredentialState.ACTIVE
                and self._active.get((binding.scope_id, binding.credential_ref)) == binding.credential_version
            )
        return record.state in (CredentialState.ACTIVE, CredentialState.PENDING)

    async def _admit_locked(
        self, context: VerifiedContext, targets: FrozenSet[Target]
    ) -> CredentialLease:
        async with self._lock:
            if self.admit_gate is not None:
                await self.admit_gate.pause()
            if self.outage:
                raise _deny(ErrorCode.CREDENTIAL_UNAVAILABLE)
            if not isinstance(context, VerifiedContext) or context.is_expired(self._clock.now()):
                raise _deny(ErrorCode.ACCESS_DENIED)
            if (
                not isinstance(targets, frozenset)
                or not targets
                or not all(isinstance(t, Target) for t in targets)
                or not targets <= context.allowed_targets
            ):
                raise _deny(ErrorCode.ACCESS_DENIED)
            binding = context.binding
            record = self._records.get(
                (binding.scope_id, binding.credential_ref, binding.credential_version)
            )
            if record is None:
                raise _deny(ErrorCode.CREDENTIAL_UNAVAILABLE)
            if record.provider != binding.provider or record.source is not binding.credential_source:
                raise _deny(ErrorCode.ACCESS_DENIED)
            if not self._state_permits(record, binding, context.kind):
                raise _deny(ErrorCode.CREDENTIAL_UNAVAILABLE)
            if not targets <= record.targets:
                raise _deny(ErrorCode.CAPABILITY_DENIED)
            self.admissions_total += 1
            admission_id = f"admission-{self.admissions_total}"
            self._in_flight.add(admission_id)
            return CredentialLease(
                binding=binding,
                state=record.state,
                secret=SecretValue(record.plaintext),
                permitted_targets=record.targets,
                admission_id=admission_id,
            )


# --- broken readers (T2.3) ----------------------------------------------------


class TamperingReader:
    """Wraps a real fake reader and returns an altered snapshot, or another object."""

    def __init__(
        self,
        inner: FakeCredentialStore,
        *,
        binding: Optional[Binding] = None,
        state: Optional[CredentialState] = None,
        targets: Optional[FrozenSet[Target]] = None,
        replacement: object = None,
    ) -> None:
        self._inner = inner
        self._binding = binding
        self._state = state
        self._targets = targets
        self._replacement = replacement

    def admit(self, context: VerifiedContext, targets: FrozenSet[Target]):  # type: ignore[no-untyped-def]
        return self._admission(context, targets)

    @contextlib.asynccontextmanager
    async def _admission(self, context: VerifiedContext, targets: FrozenSet[Target]) -> AsyncIterator[object]:
        async with self._inner.admit(context, targets) as lease:
            if self._replacement is not None:
                yield self._replacement
            else:
                yield CredentialLease(
                    binding=self._binding or lease.binding,
                    state=self._state or lease.state,
                    secret=lease.secret,
                    permitted_targets=self._targets or lease.permitted_targets,
                    admission_id=lease.admission_id,
                )


class RaisingReader:
    """A reader whose admission fails with an unexpected exception (synthetic message)."""

    def __init__(self, message: str) -> None:
        self._message = message
        self.admit_calls = 0

    def admit(self, context: VerifiedContext, targets: FrozenSet[Target]):  # type: ignore[no-untyped-def]
        self.admit_calls += 1
        return self._admission()

    @contextlib.asynccontextmanager
    async def _admission(self) -> AsyncIterator[object]:
        raise RuntimeError(self._message)
        yield  # pragma: no cover


# --- scripted provider adapter (T2.3) -----------------------------------------


@dataclass
class Script:
    """One scripted response for a single session step."""

    output: Optional[str] = field(default=None, repr=False)
    usage: Optional[UsageEntry] = None
    probe: Optional[ProbeOutcome] = None
    error: Optional[BaseException] = field(default=None, repr=False)
    gate: Optional[PauseGate] = None
    barrier: Optional[asyncio.Barrier] = None
    hang: bool = False
    raw: object = None


@dataclass
class Call:
    """A captured session call. Content and key fields are excluded from repr."""

    operation: str
    target: Target
    scope_id: str
    remaining_seconds: float
    key: str = field(repr=False)
    text: Optional[str] = field(default=None, repr=False)
    audio_length: Optional[int] = None
    audio_format: Optional[AudioFormat] = None


class ScriptedSession:
    def __init__(self, adapter: "ScriptedAdapter", lease: CredentialLease, config: ProviderConfig) -> None:
        self._adapter = adapter
        self._lease = lease
        self.config = config

    async def generate_text(self, target: Target, text: str, remaining_seconds: float) -> StepOutput:
        return await self._adapter._respond("generate_text", self._lease, target, remaining_seconds, text=text)

    async def transcribe_audio(
        self, target: Target, audio: bytes, audio_format: AudioFormat, remaining_seconds: float
    ) -> StepOutput:
        return await self._adapter._respond(
            "transcribe_audio", self._lease, target, remaining_seconds,
            audio_length=len(audio), audio_format=audio_format,
        )

    async def validate_access(self, target: Target, remaining_seconds: float) -> ProbeOutcome:
        return await self._adapter._respond("validate_access", self._lease, target, remaining_seconds)


class ScriptedAdapter:
    """ProviderAdapter double with per-step scripts and call capture. No I/O."""

    def __init__(self, targets: FrozenSet[Target]) -> None:
        self._targets = targets
        self.scripts: Dict[str, List[Script]] = {"generate_text": [], "transcribe_audio": [], "validate_access": []}
        self.calls: List[Call] = []
        self.generation_by_key: Dict[str, str] = {}
        self.default_generation = "Synthetic answer"
        self.default_transcript = "synthetic transcript"
        self.sessions_opened = 0
        self.sessions_closed = 0
        self.opened_with: List[Tuple[str, str]] = []  # (admission_id, destination)
        self.open_error: Optional[BaseException] = None
        self.close_error: Optional[BaseException] = None
        self.close_hang = False

    def calls_for(self, operation: str) -> List[Call]:
        return [call for call in self.calls if call.operation == operation]

    def supported_operations(self) -> FrozenSet[Target]:
        return self._targets

    def open_session(self, lease: CredentialLease, config: ProviderConfig):  # type: ignore[no-untyped-def]
        return self._session(lease, config)

    @contextlib.asynccontextmanager
    async def _session(self, lease: CredentialLease, config: ProviderConfig) -> AsyncIterator[ScriptedSession]:
        if self.open_error is not None:
            raise self.open_error
        self.sessions_opened += 1
        self.opened_with.append((lease.admission_id, config.destination))
        try:
            yield ScriptedSession(self, lease, config)
        finally:
            self.sessions_closed += 1
            if self.close_hang:
                await asyncio.Event().wait()
            if self.close_error is not None:
                raise self.close_error

    async def _respond(self, operation: str, lease: CredentialLease, target: Target, remaining: float, **details):  # type: ignore[no-untyped-def]
        key = lease.secret.reveal_for_session()
        self.calls.append(Call(operation, target, lease.binding.scope_id, remaining, key, **details))
        queue = self.scripts[operation]
        script = queue.pop(0) if queue else Script()
        if script.barrier is not None:
            await script.barrier.wait()
        if script.gate is not None:
            await script.gate.pause()
        if script.hang:
            await asyncio.Event().wait()
        if script.error is not None:
            raise script.error
        if script.raw is not None:
            return script.raw
        if operation == "validate_access":
            return script.probe or ProbeOutcome(ValidationStatus.VALID, None, UsageEntry(target.operation, target.model))
        usage = script.usage if script.usage is not None else UsageEntry(target.operation, target.model)
        if script.output is not None:
            text = script.output
        elif operation == "generate_text":
            text = self.generation_by_key.get(key, self.default_generation)
        else:
            text = self.default_transcript
        return StepOutput(text, usage)


# --- orchestrator test harness (T2.3) -----------------------------------------

GENERATE_TARGET = Target(Operation.GENERATE_TEXT, "gpt-4o-mini")
TRANSCRIBE_TARGET = Target(Operation.TRANSCRIBE_AUDIO, "gpt-4o-mini-transcribe")
BOTH_TARGETS = frozenset({GENERATE_TARGET, TRANSCRIBE_TARGET})
SYNTHETIC_DESTINATION = "https://provider.example.test/v1/"
KEY_SCOPE_A = "test-provider-key-scope-a-v1"
KEY_SCOPE_A_V2 = "test-provider-key-scope-a-v2"
KEY_SCOPE_B = "test-provider-key-scope-b-v1"

FAST_LIMITS = LimitProfile(
    max_text_bytes=65_536,
    max_prompt_bytes=131_072,
    max_transcript_bytes=131_072,
    max_audio_bytes=10_485_760,
    max_generation_bytes=65_536,
    max_response_body_bytes=1_048_576,
    invocation_timeout_seconds=0.5,
    validation_timeout_seconds=0.5,
    verify_timeout_seconds=0.05,
    admit_timeout_seconds=0.05,
    generation_call_timeout_seconds=0.1,
    transcription_call_timeout_seconds=0.1,
    validation_call_timeout_seconds=0.1,
    connect_timeout_seconds=0.05,
    cleanup_timeout_seconds=0.05,
    max_concurrent_operations=8,
    max_retries=0,
    follow_redirects=False,
)


def make_provider_config(provider: str = "openai", targets: FrozenSet[Target] = BOTH_TARGETS) -> ProviderConfig:
    return ProviderConfig(
        provider=provider,
        destination=SYNTHETIC_DESTINATION,
        targets=targets,
        generation=GenerationSettings(max_tokens=256, temperature=0.4, system_prompt="Synthetic system prompt."),
    )


class Harness:
    """Fake store + scripted adapters + a real Orchestrator, wired explicitly for one test."""

    def __init__(
        self,
        *,
        limits: LimitProfile = LOCAL_LIMIT_PROFILE,
        reader_factory=None,  # type: ignore[no-untyped-def]
        adapter_targets: FrozenSet[Target] = BOTH_TARGETS,
    ) -> None:
        self.clock = FakeClock()
        self.store = FakeCredentialStore(self.clock)
        self.store.add_record("scope-A", "credential-A", "v1", key=KEY_SCOPE_A, targets=BOTH_TARGETS, active=True)
        self.store.add_record("scope-B", "credential-B", "v1", key=KEY_SCOPE_B, targets=BOTH_TARGETS, active=True)
        self.adapter = ScriptedAdapter(adapter_targets)
        self.other_adapter = ScriptedAdapter(BOTH_TARGETS)
        self.config = ModuleConfig(
            limits=limits,
            providers={"openai": make_provider_config(), "other-provider": make_provider_config("other-provider")},
        )
        self.reader = reader_factory(self.store) if reader_factory else self.store
        self.orchestrator = Orchestrator(
            config=self.config,
            reader=self.reader,
            adapters={"openai": self.adapter, "other-provider": self.other_adapter},
            utc_now=self.clock.now,
        )

    def context(
        self,
        *,
        kind: ContextKind = ContextKind.INVOKE,
        targets: FrozenSet[Target] = BOTH_TARGETS,
        lifetime: float = 300,
        **binding_overrides: object,
    ) -> VerifiedContext:
        values = dict(
            scope_id="scope-A",
            credential_ref="credential-A",
            credential_version="v1",
            credential_source=CredentialSource.CUSTOMER,
            provider="openai",
        )
        values.update(binding_overrides)
        return VerifiedContext(
            binding=Binding(**values),  # type: ignore[arg-type]
            request_id=new_request_id(),
            kind=kind,
            allowed_targets=targets,
            expires_at=self.clock.now() + timedelta(seconds=lifetime),
        )

    @staticmethod
    def text_request(text: str = "Hello", generation: Target = GENERATE_TARGET) -> InvocationRequest:
        return InvocationRequest(content=InvocationInput(text=text), generation_target=generation)

    @staticmethod
    def audio_request(
        text: str = "", audio: bytes = b"\x00\x01\x02\x03", audio_format: AudioFormat = AudioFormat.WAV
    ) -> InvocationRequest:
        return InvocationRequest(
            content=InvocationInput(text=text, audio=audio, audio_format=audio_format),
            generation_target=GENERATE_TARGET,
            transcription_target=TRANSCRIBE_TARGET,
        )

    @staticmethod
    def validation_request(target: Target = GENERATE_TARGET) -> ValidationRequest:
        return ValidationRequest(target=target)


async def wait_for_calls(adapter: ScriptedAdapter, count: int, operation: Optional[str] = None) -> None:
    """Yield to the loop until ``count`` calls are recorded (bounded; no timing)."""
    for _ in range(10_000):
        calls = adapter.calls_for(operation) if operation else adapter.calls
        if len(calls) >= count:
            return
        await asyncio.sleep(0)
    raise AssertionError("expected provider calls were not reached")
