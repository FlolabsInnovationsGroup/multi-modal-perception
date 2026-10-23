"""Request orchestration: checks, admission, ordering, deadlines, cleanup (L1-L5).

The orchestrator receives an already verified context. It never retries,
never selects another provider, credential, source or model, never echoes
input as a result, and never activates a credential. Every exit closes the
session and lease (bounded) and releases shared capacity.

T2.3 decisions (approved 2026-10-23):

- D1: a ProviderOperationError, a per-step timeout or an unexpected exception
  counts as an attempted provider step and adds a usage entry (null
  quantities when nothing was reported). A plain ProviderIntegrationError from
  a session means nothing was sent and adds no entry.
- D2: per-step timeout -> PROVIDER_TIMEOUT; overall deadline ->
  OPERATION_TIMEOUT; admission timeout -> CREDENTIAL_UNAVAILABLE.
- D3: a cleanup failure after a result keeps the result; the cleanup error is
  suppressed without being retained, and capacity is still released.
- D4: a probe that raises CREDENTIAL_REJECTED or CAPABILITY_DENIED is
  ``rejected``; any other failure is ``indeterminate``. Local (pre-provider)
  denials in validation are never ``rejected``.
- D5: deadlines use the event loop's monotonic clock; context expiry and
  ``checked_at`` use the injected UTC clock.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Awaitable, Callable, FrozenSet, List, Mapping, Optional, TypeVar

from services.provider_integration.config import ModuleConfig, ProviderConfig
from services.provider_integration.errors import (
    ErrorCode,
    ProviderIntegrationError,
    ProviderOperationError,
)
from services.provider_integration.ports import CredentialReader, ProviderAdapter, ProviderSession
from services.provider_integration.types import (
    ContextKind,
    CredentialLease,
    CredentialState,
    FileType,
    InvocationRequest,
    InvocationResult,
    Outcome,
    ProbeOutcome,
    SecretValue,
    StepOutput,
    Target,
    UsageEntry,
    ValidationRequest,
    ValidationResult,
    ValidationStatus,
    VerifiedContext,
    is_valid_identifier,
)

# Existing /process behaviour (L4): audio without text uses this instruction.
AUDIO_INSTRUCTION = "reply to the audio"
TRANSCRIPT_SEPARATOR = "\n\nAudio transcript:\n"

_REJECTION_CODES = frozenset({ErrorCode.CREDENTIAL_REJECTED, ErrorCode.CAPABILITY_DENIED})
_INVOKE_STATES = frozenset({CredentialState.ACTIVE})
_VALIDATE_STATES = frozenset({CredentialState.ACTIVE, CredentialState.PENDING})

_T = TypeVar("_T")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _loop_time() -> float:
    return asyncio.get_running_loop().time()


def _utf8_length(text: str) -> Optional[int]:
    try:
        return len(text.encode("utf-8"))
    except UnicodeEncodeError:
        return None


class _Failure(Exception):
    """Internal control flow carrying an allowlisted code; never leaves this module."""

    def __init__(self, code: ErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


class CapacityGate:
    """Shared, non-queuing per-process limit on in-flight operations."""

    def __init__(self, limit: int) -> None:
        if type(limit) is not int or limit <= 0:
            raise ValueError("limit must be a positive int")
        self._limit = limit
        self._in_use = 0

    @property
    def in_use(self) -> int:
        return self._in_use

    def try_acquire(self) -> bool:
        if self._in_use >= self._limit:
            return False
        self._in_use += 1
        return True

    def release(self) -> None:
        if self._in_use > 0:
            self._in_use -= 1


class Orchestrator:
    """Runs one verified invocation or validation with explicitly injected dependencies."""

    def __init__(
        self,
        *,
        config: ModuleConfig,
        reader: CredentialReader,
        adapters: Mapping[str, ProviderAdapter],
        utc_now: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not isinstance(config, ModuleConfig):
            raise TypeError("config must be a ModuleConfig")
        if not isinstance(reader, CredentialReader):
            raise TypeError("reader must implement CredentialReader")
        if not isinstance(adapters, Mapping):
            raise TypeError("adapters must be a mapping")
        copied = dict(adapters)
        for name, adapter in copied.items():
            if not is_valid_identifier(name) or not isinstance(adapter, ProviderAdapter):
                raise TypeError("adapters must map provider identifiers to ProviderAdapter")
        self._config = config
        self._reader = reader
        self._adapters: Mapping[str, ProviderAdapter] = MappingProxyType(copied)
        self._utc_now = utc_now
        self._capacity = CapacityGate(config.limits.max_concurrent_operations)

    @property
    def capacity_in_use(self) -> int:
        return self._capacity.in_use

    # -- public operations -------------------------------------------------------

    async def invoke(
        self,
        context: VerifiedContext,
        request: InvocationRequest,
        *,
        started_at: Optional[float] = None,
    ) -> InvocationResult:
        """Run one invocation. ``started_at`` is the loop time at handler entry, if any."""
        if not isinstance(context, VerifiedContext) or not isinstance(request, InvocationRequest):
            raise TypeError("invoke requires a VerifiedContext and an InvocationRequest")
        limits = self._config.limits
        start = _loop_time() if started_at is None else started_at
        deadline = start + limits.invocation_timeout_seconds
        usage: List[UsageEntry] = []

        def failure(code: ErrorCode) -> InvocationResult:
            return self._invocation_result(context, request, code=code, usage=usage)

        code = self._precheck(context, request.targets, ContextKind.INVOKE) or self._input_check(request)
        if code is not None:
            return failure(code)
        if not self._capacity.try_acquire():
            return failure(ErrorCode.CAPACITY_EXCEEDED)

        stack = contextlib.AsyncExitStack()
        try:
            try:
                text = await self._run_invocation(stack, context, request, deadline, usage)
            except _Failure as caught:
                return failure(caught.code)
            except Exception:  # unexpected local failure; never retained
                return failure(ErrorCode.INTERNAL_ERROR)
            return self._invocation_result(context, request, result=text, usage=usage)
        finally:
            await self._close(stack)
            self._capacity.release()

    async def validate(
        self,
        context: VerifiedContext,
        request: ValidationRequest,
        *,
        started_at: Optional[float] = None,
    ) -> ValidationResult:
        """Run exactly one validation probe for the exact bound version."""
        if not isinstance(context, VerifiedContext) or not isinstance(request, ValidationRequest):
            raise TypeError("validate requires a VerifiedContext and a ValidationRequest")
        limits = self._config.limits
        start = _loop_time() if started_at is None else started_at
        deadline = start + limits.validation_timeout_seconds
        target = request.target

        def indeterminate(code: ErrorCode, usage: tuple = ()) -> ValidationResult:
            # Local denials are never a definitive provider rejection (D4).
            reason = ErrorCode.ACCESS_DENIED if code in _REJECTION_CODES else code
            return self._validation_result(context, target, ValidationStatus.INDETERMINATE, reason, usage)

        code = self._precheck(context, frozenset({target}), ContextKind.VALIDATE)
        if code is not None:
            return indeterminate(code)
        if not self._capacity.try_acquire():
            return indeterminate(ErrorCode.CAPACITY_EXCEEDED)

        stack = contextlib.AsyncExitStack()
        try:
            try:
                session, lease = await self._open(stack, context, frozenset({target}), ContextKind.VALIDATE, deadline)
            except _Failure as caught:
                return indeterminate(caught.code)
            except Exception:
                return indeterminate(ErrorCode.INTERNAL_ERROR)
            return await self._probe(session, lease, context, target, deadline)
        finally:
            await self._close(stack)
            self._capacity.release()

    # -- checks ------------------------------------------------------------------

    def _precheck(self, context: VerifiedContext, targets: FrozenSet[Target], kind: ContextKind) -> Optional[ErrorCode]:
        if context.kind is not kind or context.is_expired(self._utc_now()):
            return ErrorCode.ACCESS_DENIED
        if not targets <= context.allowed_targets:
            return ErrorCode.ACCESS_DENIED
        provider = context.binding.provider
        config = self._config.provider_config(provider)
        adapter = self._adapters.get(provider)
        if config is None or adapter is None:
            return ErrorCode.NOT_CONFIGURED
        try:
            supported = adapter.supported_operations()
        except Exception:
            return ErrorCode.NOT_CONFIGURED
        if not isinstance(supported, frozenset):
            return ErrorCode.NOT_CONFIGURED
        if not all(config.supports(target) and target in supported for target in targets):
            return ErrorCode.UNSUPPORTED_OPERATION
        return None

    def _input_check(self, request: InvocationRequest) -> Optional[ErrorCode]:
        limits = self._config.limits
        text_bytes = _utf8_length(request.content.text)
        if text_bytes is None or text_bytes > limits.max_text_bytes:
            return ErrorCode.INVALID_INPUT
        if request.content.has_audio and len(request.content.audio) > limits.max_audio_bytes:  # type: ignore[arg-type]
            return ErrorCode.INVALID_INPUT
        return None

    @staticmethod
    def _check_lease(lease: object, context: VerifiedContext, targets: FrozenSet[Target], kind: ContextKind) -> CredentialLease:
        # Defense against a broken reader: the returned snapshot must match exactly.
        if not isinstance(lease, CredentialLease) or lease.binding != context.binding:
            raise _Failure(ErrorCode.ACCESS_DENIED)
        allowed = _INVOKE_STATES if kind is ContextKind.INVOKE else _VALIDATE_STATES
        if lease.state not in allowed:
            raise _Failure(ErrorCode.CREDENTIAL_UNAVAILABLE)
        if not targets <= lease.permitted_targets:
            raise _Failure(ErrorCode.CAPABILITY_DENIED)
        return lease

    # -- phases ------------------------------------------------------------------

    async def _bounded(
        self,
        call: Callable[[], Awaitable[_T]],
        deadline: float,
        phase_limit: float,
        timeout_code: ErrorCode,
        error_code: ErrorCode,
    ) -> _T:
        """Await one non-provider phase within min(phase limit, remaining overall time)."""
        now = _loop_time()
        if now >= deadline:
            raise _Failure(ErrorCode.OPERATION_TIMEOUT)
        phase_deadline = min(deadline, now + phase_limit)
        try:
            async with asyncio.timeout_at(phase_deadline):
                return await call()
        except TimeoutError:
            raise _Failure(ErrorCode.OPERATION_TIMEOUT if phase_deadline >= deadline else timeout_code) from None
        except ProviderIntegrationError as caught:
            raise _Failure(caught.code) from None
        except Exception:
            raise _Failure(error_code) from None

    async def _open(
        self,
        stack: contextlib.AsyncExitStack,
        context: VerifiedContext,
        targets: FrozenSet[Target],
        kind: ContextKind,
        deadline: float,
    ) -> tuple:
        limits = self._config.limits
        provider = context.binding.provider
        lease = await self._bounded(
            lambda: stack.enter_async_context(self._reader.admit(context, targets)),
            deadline,
            limits.admit_timeout_seconds,
            ErrorCode.CREDENTIAL_UNAVAILABLE,
            ErrorCode.CREDENTIAL_UNAVAILABLE,
        )
        lease = self._check_lease(lease, context, targets, kind)
        provider_config: ProviderConfig = self._config.provider_config(provider)  # type: ignore[assignment]
        adapter = self._adapters[provider]
        session = await self._bounded(
            lambda: stack.enter_async_context(adapter.open_session(lease, provider_config)),
            deadline,
            limits.connect_timeout_seconds,
            ErrorCode.PROVIDER_UNAVAILABLE,
            ErrorCode.INTERNAL_ERROR,
        )
        if not isinstance(session, ProviderSession):
            raise _Failure(ErrorCode.INTERNAL_ERROR)
        return session, lease

    @staticmethod
    def _clean_usage(entry: object, target: Target, secret: SecretValue) -> UsageEntry:
        # Usage must describe the attempted target; anything else becomes null usage.
        if not isinstance(entry, UsageEntry) or entry.operation is not target.operation or entry.model != target.model:
            return UsageEntry(target.operation, target.model)
        if entry.provider_request_id is not None and secret.appears_in(entry.provider_request_id):
            return dataclasses.replace(entry, provider_request_id=None)
        return entry

    async def _step(
        self,
        call: Callable[[float], Awaitable[object]],
        target: Target,
        deadline: float,
        call_limit: float,
        usage: List[UsageEntry],
        secret: SecretValue,
    ) -> str:
        """One provider step (D1/D2): at most one attempt, bounded, usage recorded."""
        now = _loop_time()
        if now >= deadline:
            raise _Failure(ErrorCode.OPERATION_TIMEOUT)
        overall_bound = deadline - now <= call_limit
        remaining = min(call_limit, deadline - now)
        step_deadline = now + remaining
        try:
            async with asyncio.timeout_at(step_deadline):
                output = await call(remaining)
        except TimeoutError:
            usage.append(UsageEntry(target.operation, target.model))
            raise _Failure(
                ErrorCode.OPERATION_TIMEOUT if overall_bound else ErrorCode.PROVIDER_TIMEOUT
            ) from None
        except ProviderOperationError as caught:
            usage.append(self._clean_usage(caught.usage, target, secret))
            raise _Failure(caught.code) from None
        except ProviderIntegrationError as caught:
            raise _Failure(caught.code) from None
        except Exception:
            usage.append(UsageEntry(target.operation, target.model))
            raise _Failure(ErrorCode.INTERNAL_ERROR) from None
        if not isinstance(output, StepOutput):
            usage.append(UsageEntry(target.operation, target.model))
            raise _Failure(ErrorCode.PROVIDER_RESPONSE_INVALID)
        usage.append(self._clean_usage(output.usage, target, secret))
        return output.text

    async def _run_invocation(
        self,
        stack: contextlib.AsyncExitStack,
        context: VerifiedContext,
        request: InvocationRequest,
        deadline: float,
        usage: List[UsageEntry],
    ) -> str:
        limits = self._config.limits
        session, lease = await self._open(stack, context, request.targets, ContextKind.INVOKE, deadline)
        content = request.content
        text = content.text.strip()

        if content.has_audio:
            transcription_target = request.transcription_target
            raw_transcript = await self._step(
                lambda remaining: session.transcribe_audio(
                    transcription_target, content.audio, content.audio_format, remaining
                ),
                transcription_target,  # type: ignore[arg-type]
                deadline,
                limits.transcription_call_timeout_seconds,
                usage,
                lease.secret,
            )
            transcript_bytes = _utf8_length(raw_transcript)
            if transcript_bytes is None or transcript_bytes > limits.max_transcript_bytes:
                raise _Failure(ErrorCode.INVALID_INPUT)
            instruction = text or AUDIO_INSTRUCTION
            transcript = raw_transcript.strip()
            prompt = instruction + TRANSCRIPT_SEPARATOR + transcript if transcript else instruction
        else:
            prompt = text

        prompt_bytes = _utf8_length(prompt)
        if prompt_bytes is None or prompt_bytes > limits.max_prompt_bytes:
            raise _Failure(ErrorCode.INVALID_INPUT)

        generation_target = request.generation_target
        generated = await self._step(
            lambda remaining: session.generate_text(generation_target, prompt, remaining),
            generation_target,
            deadline,
            limits.generation_call_timeout_seconds,
            usage,
            lease.secret,
        )
        result = generated.strip()
        result_bytes = _utf8_length(result)
        if not result or result_bytes is None or result_bytes > limits.max_generation_bytes:
            raise _Failure(ErrorCode.PROVIDER_RESPONSE_INVALID)
        if lease.secret.appears_in(result):
            raise _Failure(ErrorCode.INTERNAL_ERROR)
        return result

    async def _probe(
        self,
        session: ProviderSession,
        lease: CredentialLease,
        context: VerifiedContext,
        target: Target,
        deadline: float,
    ) -> ValidationResult:
        limits = self._config.limits
        now = _loop_time()
        if now >= deadline:
            return self._validation_result(context, target, ValidationStatus.INDETERMINATE, ErrorCode.OPERATION_TIMEOUT, ())
        overall_bound = deadline - now <= limits.validation_call_timeout_seconds
        remaining = min(limits.validation_call_timeout_seconds, deadline - now)
        probe_deadline = now + remaining
        null_usage = (UsageEntry(target.operation, target.model),)
        try:
            async with asyncio.timeout_at(probe_deadline):
                outcome = await session.validate_access(target, remaining)
        except TimeoutError:
            code = ErrorCode.OPERATION_TIMEOUT if overall_bound else ErrorCode.PROVIDER_TIMEOUT
            return self._validation_result(context, target, ValidationStatus.INDETERMINATE, code, null_usage)
        except ProviderOperationError as caught:
            usage = (self._clean_usage(caught.usage, target, lease.secret),)
            return self._validation_from_code(context, target, caught.code, usage)
        except ProviderIntegrationError as caught:
            return self._validation_from_code(context, target, caught.code, ())
        except Exception:
            return self._validation_result(
                context, target, ValidationStatus.INDETERMINATE, ErrorCode.INTERNAL_ERROR, null_usage
            )
        if not isinstance(outcome, ProbeOutcome):
            return self._validation_result(
                context, target, ValidationStatus.INDETERMINATE, ErrorCode.PROVIDER_RESPONSE_INVALID, null_usage
            )
        usage = (self._clean_usage(outcome.usage, target, lease.secret),)
        return self._validation_result(context, target, outcome.status, outcome.reason_code, usage)

    def _validation_from_code(
        self, context: VerifiedContext, target: Target, code: ErrorCode, usage: tuple
    ) -> ValidationResult:
        status = ValidationStatus.REJECTED if code in _REJECTION_CODES else ValidationStatus.INDETERMINATE
        return self._validation_result(context, target, status, code, usage)

    # -- results and cleanup -------------------------------------------------------

    @staticmethod
    def _invocation_result(
        context: VerifiedContext,
        request: InvocationRequest,
        *,
        result: Optional[str] = None,
        code: Optional[ErrorCode] = None,
        usage: List[UsageEntry],
    ) -> InvocationResult:
        file_type = FileType.AUDIO if request.content.has_audio else FileType.TEXT
        if code is None:
            return InvocationResult(
                request_id=context.request_id,
                provider=context.binding.provider,
                model=request.generation_target.model,
                file_type=file_type,
                outcome=Outcome.SUCCESS,
                result=result,
                usage=tuple(usage),
            )
        return InvocationResult(
            request_id=context.request_id,
            provider=context.binding.provider,
            model=request.generation_target.model,
            file_type=file_type,
            outcome=Outcome.ERROR,
            error_code=code,
            usage=tuple(usage),
        )

    def _validation_result(
        self,
        context: VerifiedContext,
        target: Target,
        status: ValidationStatus,
        reason: Optional[ErrorCode],
        usage: tuple,
    ) -> ValidationResult:
        return ValidationResult(
            request_id=context.request_id,
            binding=context.binding,
            target=target,
            checked_at=self._utc_now(),
            status=status,
            reason_code=reason,
            usage=usage,
        )

    async def _close(self, stack: contextlib.AsyncExitStack) -> None:
        """Bounded cleanup (D3): errors and timeouts are suppressed, never retained."""
        try:
            async with asyncio.timeout(self._config.limits.cleanup_timeout_seconds):
                await stack.aclose()
        except Exception:
            pass
