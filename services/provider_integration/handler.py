"""Internal verified handler and legacy-success projection (T4.1; L2, L4, L5).

Not a public route. A future approved backend bridge passes untrusted plain
mappings; this module parses them with exact field allowlists, verifies the
caller through the injected ContextVerifier, and only then runs the
orchestrator. Nothing here reads the environment or imports provider SDKs.

T4.1 decisions (approved 2026-10-23):

- C1: the requested binding and the request are untrusted mappings with exact
  allowed fields; anything else is BoundaryFailure(INVALID_INPUT).
- C2: parse -> verify (bounded) -> defensive context re-check -> orchestrator
  with ``started_at`` = handler entry. Any verifier denial, timeout, exception
  or mismatching context is BoundaryFailure(ACCESS_DENIED).
- C3: empty audio counts as no audio (audio_format / transcription_model are
  ignored, as in the current /process route); a transcription model or audio
  format without any audio field is INVALID_INPUT.
- C4: legacy_success imports schemas.PerceptionOutput only when called and
  projects only result/model/file_type; anything but a success raises.
"""

from __future__ import annotations

import asyncio
from typing import FrozenSet, Mapping, Optional, Union

from services.provider_integration.config import LimitProfile
from services.provider_integration.errors import ErrorCode
from services.provider_integration.orchestrator import Orchestrator
from services.provider_integration.ports import ContextVerifier
from services.provider_integration.types import (
    AudioFormat,
    Binding,
    BoundaryFailure,
    ContextKind,
    CredentialSource,
    InvocationInput,
    InvocationRequest,
    InvocationResult,
    Operation,
    Outcome,
    Target,
    ValidationRequest,
    ValidationResult,
    VerifiedContext,
)

BINDING_FIELDS = frozenset({"scope_id", "credential_ref", "credential_version", "credential_source", "provider"})
INVOKE_FIELDS = frozenset({"text", "audio", "audio_format", "generation_model", "transcription_model"})
VALIDATE_FIELDS = frozenset({"operation", "model"})


class _ParseError(Exception):
    """Internal: the untrusted input was rejected. Never carries the input."""


def _fields(data: object, allowed: FrozenSet[str], required: FrozenSet[str]) -> Mapping[str, object]:
    if not isinstance(data, Mapping):
        raise _ParseError()
    keys = set(data)
    if not all(isinstance(key, str) for key in keys) or keys - allowed or required - keys:
        raise _ParseError()
    return data


def parse_binding(data: object) -> Binding:
    fields = _fields(data, BINDING_FIELDS, BINDING_FIELDS)
    source = fields["credential_source"]
    if type(source) is not str:  # plain route-body strings only (C1), not enum or str subclasses
        raise _ParseError()
    try:
        return Binding(
            scope_id=fields["scope_id"],  # type: ignore[arg-type]
            credential_ref=fields["credential_ref"],  # type: ignore[arg-type]
            credential_version=fields["credential_version"],  # type: ignore[arg-type]
            credential_source=CredentialSource(source),
            provider=fields["provider"],  # type: ignore[arg-type]
        )
    except (TypeError, ValueError):
        raise _ParseError() from None


def _utf8_length(text: str) -> Optional[int]:
    try:
        return len(text.encode("utf-8"))
    except UnicodeEncodeError:
        return None


def parse_invocation(data: object, limits: LimitProfile) -> InvocationRequest:
    fields = _fields(data, INVOKE_FIELDS, frozenset({"generation_model"}))
    text = fields.get("text")
    text = "" if text is None else text
    audio = fields.get("audio")
    audio_format = fields.get("audio_format")
    transcription_model = fields.get("transcription_model")
    if type(text) is not str or (audio is not None and type(audio) is not bytes):
        raise _ParseError()
    # L5: raw text is measured before stripping; audio before any copy.
    text_bytes = _utf8_length(text)
    if text_bytes is None or text_bytes > limits.max_text_bytes:
        raise _ParseError()
    if audio is not None and len(audio) > limits.max_audio_bytes:
        raise _ParseError()
    if audio is None and (audio_format is not None or transcription_model is not None):
        raise _ParseError()  # C3: audio settings without any audio field

    try:
        generation = Target(Operation.GENERATE_TEXT, fields["generation_model"])  # type: ignore[arg-type]
        if not audio:  # None or b"": no audio (C3, L4)
            return InvocationRequest(content=InvocationInput(text=text.strip()), generation_target=generation)
        if type(audio_format) is not str:
            raise _ParseError()
        content = InvocationInput(text=text.strip(), audio=audio, audio_format=AudioFormat(audio_format))
        transcription = Target(Operation.TRANSCRIBE_AUDIO, transcription_model)  # type: ignore[arg-type]
        return InvocationRequest(content=content, generation_target=generation, transcription_target=transcription)
    except (TypeError, ValueError):
        raise _ParseError() from None


def parse_validation(data: object) -> ValidationRequest:
    fields = _fields(data, VALIDATE_FIELDS, VALIDATE_FIELDS)
    operation = fields["operation"]
    if type(operation) is not str:
        raise _ParseError()
    try:
        return ValidationRequest(target=Target(Operation(operation), fields["model"]))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise _ParseError() from None


class Handler:
    """Internal entry point: verification always precedes credential access."""

    def __init__(self, *, verifier: ContextVerifier, orchestrator: Orchestrator, limits: LimitProfile) -> None:
        if not isinstance(verifier, ContextVerifier):
            raise TypeError("verifier must implement ContextVerifier")
        if not isinstance(orchestrator, Orchestrator):
            raise TypeError("orchestrator must be an Orchestrator")
        if not isinstance(limits, LimitProfile):
            raise TypeError("limits must be a LimitProfile")
        self._verifier = verifier
        self._orchestrator = orchestrator
        self._limits = limits

    async def process(
        self, call_evidence: object, requested_binding: object, request: object
    ) -> Union[InvocationResult, BoundaryFailure]:
        start = asyncio.get_running_loop().time()
        try:
            binding = parse_binding(requested_binding)
            invocation = parse_invocation(request, self._limits)
        except _ParseError:
            return BoundaryFailure.create(ErrorCode.INVALID_INPUT)
        deadline = start + self._limits.invocation_timeout_seconds
        context = await self._verify(call_evidence, binding, ContextKind.INVOKE, invocation.targets, deadline)
        if context is None:
            return BoundaryFailure.create(ErrorCode.ACCESS_DENIED)
        return await self._orchestrator.invoke(context, invocation, started_at=start)

    async def validate(
        self, call_evidence: object, requested_binding: object, request: object
    ) -> Union[ValidationResult, BoundaryFailure]:
        start = asyncio.get_running_loop().time()
        try:
            binding = parse_binding(requested_binding)
            validation = parse_validation(request)
        except _ParseError:
            return BoundaryFailure.create(ErrorCode.INVALID_INPUT)
        deadline = start + self._limits.validation_timeout_seconds
        targets = frozenset({validation.target})
        context = await self._verify(call_evidence, binding, ContextKind.VALIDATE, targets, deadline)
        if context is None:
            return BoundaryFailure.create(ErrorCode.ACCESS_DENIED)
        return await self._orchestrator.validate(context, validation, started_at=start)

    async def _verify(
        self,
        call_evidence: object,
        binding: Binding,
        kind: ContextKind,
        targets: FrozenSet[Target],
        deadline: float,
    ) -> Optional[VerifiedContext]:
        now = asyncio.get_running_loop().time()
        if now >= deadline:
            return None
        phase_deadline = min(deadline, now + self._limits.verify_timeout_seconds)
        try:
            async with asyncio.timeout_at(phase_deadline):
                context = await self._verifier.verify(call_evidence, binding, kind, targets)
        except Exception:  # denial, timeout or unexpected failure: never retained or reflected
            return None
        # Defensive re-check: a verifier must return exactly the requested scope and kind.
        if (
            not isinstance(context, VerifiedContext)
            or context.binding != binding
            or context.kind is not kind
            or not targets <= context.allowed_targets
        ):
            return None
        return context


def legacy_success(result: object) -> object:
    """Project a successful InvocationResult onto the existing PerceptionOutput (L4)."""
    if not isinstance(result, InvocationResult) or result.outcome is not Outcome.SUCCESS:
        raise TypeError("only a successful InvocationResult can be projected")
    from schemas import PerceptionOutput  # C4: pydantic is loaded only when projecting

    return PerceptionOutput(result=result.result, model=result.model, file_type=result.file_type.value)
