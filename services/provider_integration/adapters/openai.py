"""OpenAI adapter (T3.1-T3.2, L6). The only module that imports the OpenAI SDK.

Reworked by Mani on 2026-10-23 from the T3.1 draft by Sukhpreet (commit
f7fde62, cherry-picked with authorship). Kept from the draft: the quota-code
allowlist, the status cases, the probe parameters and the silent-WAV builder.

One AsyncOpenAI client per credential lease, with the lease's key and the
configured destination passed explicitly, zero SDK retries, and an owned httpx
client (no environment proxies/TLS settings, no redirects, TLS verification
on) whose transport is wrapped by a per-session guard. Failures are reported
with allowlisted codes only; raw messages, bodies and keys are never retained.

T3.1 decisions (approved 2026-10-23): A1 no built-in models (configuration
only); A2 HTTP 403 -> ACCESS_DENIED; A3 opening a session fails closed with
NOT_CONFIGURED while the openai/httpx/httpcore loggers emit DEBUG records;
A4 environment-derived organization/project are cleared; A5 ``transport`` is
a test-only seam that wiring never sets.

T3.2 decisions (approved 2026-10-23): B1 a response over the byte cap ->
PROVIDER_RESPONSE_INVALID; B2 ``Accept-Encoding: identity`` is forced and any
other Content-Encoding is refused; B3 a request outside the configured
destination is blocked before sending -> INTERNAL_ERROR; B4 organization/project
headers are removed at the transport; B5 the text probe has no system prompt
and the audio probe uploads ``input.wav``; B6 probe failures are returned as
ProbeOutcome (rejected only for CREDENTIAL_REJECTED / CAPABILITY_DENIED).
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import math
import wave
from typing import AsyncIterator, FrozenSet, Optional

import httpx
import openai
from openai import AsyncOpenAI

from services.provider_integration.config import ProviderConfig
from services.provider_integration.errors import (
    ErrorCode,
    ProviderIntegrationError,
    ProviderOperationError,
)
from services.provider_integration.types import (
    AudioFormat,
    CredentialLease,
    Operation,
    ProbeOutcome,
    SecretValue,
    StepOutput,
    Target,
    UsageEntry,
    ValidationStatus,
    is_valid_identifier,
)

PROVIDER = "openai"
IMPLEMENTED_OPERATIONS = frozenset({Operation.GENERATE_TEXT, Operation.TRANSCRIBE_AUDIO})

# L6 quota/billing allowlist (from the T3.1 draft; matches the 2026-10-23 error-codes guide).
QUOTA_CODES = frozenset(
    {
        "insufficient_quota",
        "credit_balance_exhausted",
        "organization_spend_limit_exceeded",
        "project_spend_limit_exceeded",
        "organization_usage_limit_exceeded",
    }
)

# L6 validation probes (B5).
TEXT_PROBE_PROMPT = "Reply with OK."
TEXT_PROBE_MAX_TOKENS = 8
AUDIO_PROBE_FILENAME = "input.wav"

_REJECTION_CODES = frozenset({ErrorCode.CREDENTIAL_REJECTED, ErrorCode.CAPABILITY_DENIED})
_VERBOSE_LOGGERS = ("openai", "httpx", "httpcore")
_STRIPPED_HEADERS = ("OpenAI-Organization", "OpenAI-Project")
_DEFAULT_PORTS = {"https": 443, "http": 80}


def _bounded_token(value: object) -> Optional[str]:
    """Keep a provider code/type only if it is a short plain identifier."""
    return value if is_valid_identifier(value) else None  # type: ignore[return-value]


def classify_error(exc: BaseException) -> ErrorCode:
    """Map an SDK/transport exception to an allowlisted code (L6, A2).

    Reads only the status and a bounded ``code``/``type``; never the message or body.
    """
    if isinstance(exc, openai.APITimeoutError):  # subclass of APIConnectionError: check first
        return ErrorCode.PROVIDER_TIMEOUT
    if isinstance(exc, openai.APIConnectionError):
        return ErrorCode.PROVIDER_UNAVAILABLE
    if isinstance(exc, openai.APIStatusError):
        status = exc.status_code if type(exc.status_code) is int else None
        code = _bounded_token(getattr(exc, "code", None))
        kind = _bounded_token(getattr(exc, "type", None))
        if status == 401:
            return ErrorCode.CREDENTIAL_REJECTED if code == "invalid_api_key" else ErrorCode.ACCESS_DENIED
        if status == 403:
            return ErrorCode.ACCESS_DENIED
        if status == 404:
            return ErrorCode.CAPABILITY_DENIED if code == "model_not_found" else ErrorCode.PROVIDER_RESPONSE_INVALID
        if status == 429:
            if code in QUOTA_CODES or kind == "insufficient_quota":
                return ErrorCode.QUOTA_EXCEEDED
            return ErrorCode.RATE_LIMITED
        if status == 408 or (status is not None and 500 <= status <= 599):
            return ErrorCode.PROVIDER_UNAVAILABLE
        if status in (400, 413, 422):
            return ErrorCode.INVALID_INPUT
        return ErrorCode.PROVIDER_RESPONSE_INVALID
    if isinstance(exc, (openai.APIResponseValidationError, json.JSONDecodeError)):
        return ErrorCode.PROVIDER_RESPONSE_INVALID
    return ErrorCode.INTERNAL_ERROR


def build_silent_wav(duration_seconds: float = 1.0, sample_rate: int = 16_000) -> bytes:
    """One-second mono 16-bit PCM silence, generated in memory (L6 audio probe; from the draft)."""
    frame_count = int(sample_rate * duration_seconds)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count)
    return buffer.getvalue()


def _verbose_logging_enabled() -> bool:
    return any(logging.getLogger(name).isEnabledFor(logging.DEBUG) for name in _VERBOSE_LOGGERS)


# --- guarded transport (T3.2) -------------------------------------------------


class GuardViolation(Exception):
    """Raised inside the transport; the session reports it through the guard's flags."""


class _CappedStream(httpx.AsyncByteStream):
    """Counts raw response bytes as they arrive and stops once the cap is exceeded."""

    def __init__(self, inner: httpx.AsyncByteStream, limit: int, guard: "GuardedTransport") -> None:
        self._inner = inner
        self._limit = limit
        self._guard = guard

    async def __aiter__(self) -> AsyncIterator[bytes]:
        total = 0
        async for chunk in self._inner:
            total += len(chunk)
            if total > self._limit:
                self._guard.response_invalid = True
                raise GuardViolation()
            yield chunk

    async def aclose(self) -> None:
        close = getattr(self._inner, "aclose", None)
        if close is not None:
            await close()


class GuardedTransport(httpx.AsyncBaseTransport):
    """Per-session guard: approved destination only, header hygiene, bounded responses."""

    def __init__(self, inner: httpx.AsyncBaseTransport, destination: str, max_response_bytes: int) -> None:
        url = httpx.URL(destination)
        self._inner = inner
        self._scheme = url.scheme
        self._host = url.host
        self._port = url.port or _DEFAULT_PORTS.get(url.scheme)
        self._prefix = url.path if url.path.endswith("/") else url.path + "/"
        self._limit = max_response_bytes
        self.response_invalid = False
        self.blocked = False

    def reset(self) -> None:
        self.response_invalid = False
        self.blocked = False

    def _approved(self, url: httpx.URL) -> bool:
        return (
            url.scheme == self._scheme
            and url.host == self._host
            and (url.port or _DEFAULT_PORTS.get(url.scheme)) == self._port
            and url.path.startswith(self._prefix)
            and not url.userinfo
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if not self._approved(request.url):
            self.blocked = True  # B3: never sent
            raise GuardViolation()
        for name in _STRIPPED_HEADERS:  # B4
            if name in request.headers:
                del request.headers[name]
        request.headers["Accept-Encoding"] = "identity"  # B2

        response = await self._inner.handle_async_request(request)
        encoding = response.headers.get("content-encoding", "identity").strip().lower()
        declared = response.headers.get("content-length")
        too_long = False
        if declared is not None:
            try:
                too_long = int(declared) > self._limit
            except ValueError:
                too_long = True
        if encoding not in ("", "identity") or too_long:
            await response.aclose()
            self.response_invalid = True  # B1/B2: refused before reading the body
            raise GuardViolation()
        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            stream=_CappedStream(response.stream, self._limit, self),  # type: ignore[arg-type]
            extensions=response.extensions,
            request=request,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()


# --- session --------------------------------------------------------------------


class OpenAISession:
    """Request-local session bound to one lease and one provider configuration."""

    def __init__(
        self,
        client: AsyncOpenAI,
        lease: CredentialLease,
        config: ProviderConfig,
        targets: FrozenSet[Target],
        connect_timeout_seconds: float,
        guard: GuardedTransport,
    ) -> None:
        self._client = client
        self._lease = lease
        self._config = config
        self._targets = targets
        self._connect_timeout = connect_timeout_seconds
        self._guard = guard

    # -- helpers -------------------------------------------------------------------

    def _check_target(self, target: object, operation: Optional[Operation] = None) -> Target:
        if (
            not isinstance(target, Target)
            or (operation is not None and target.operation is not operation)
            or target.operation not in IMPLEMENTED_OPERATIONS
            or target not in self._targets
            or not self._config.supports(target)
            or target not in self._lease.permitted_targets
        ):
            raise ProviderIntegrationError(ErrorCode.UNSUPPORTED_OPERATION)
        return target

    def _timeout(self, remaining_seconds: object) -> httpx.Timeout:
        if type(remaining_seconds) not in (int, float) or not math.isfinite(remaining_seconds) or remaining_seconds <= 0:  # type: ignore[arg-type]
            raise ProviderIntegrationError(ErrorCode.OPERATION_TIMEOUT)
        remaining = float(remaining_seconds)  # type: ignore[arg-type]
        return httpx.Timeout(remaining, connect=min(self._connect_timeout, remaining))

    @property
    def _secret(self) -> SecretValue:
        return self._lease.secret

    def _code(self, exc: BaseException) -> ErrorCode:
        if self._guard.blocked:
            return ErrorCode.INTERNAL_ERROR  # B3
        if self._guard.response_invalid:
            return ErrorCode.PROVIDER_RESPONSE_INVALID  # B1/B2
        return classify_error(exc)

    def _failure_usage(self, exc: BaseException, target: Target) -> UsageEntry:
        request_id = getattr(exc, "request_id", None) if isinstance(exc, openai.APIStatusError) else None
        return UsageEntry.from_reported(target.operation, target.model, provider_request_id=request_id, secret=self._secret)

    def _chat_usage(self, response: object, target: Target) -> UsageEntry:
        reported = getattr(response, "usage", None)
        return UsageEntry.from_reported(
            target.operation,
            target.model,
            input_tokens=getattr(reported, "prompt_tokens", None),
            output_tokens=getattr(reported, "completion_tokens", None),
            total_tokens=getattr(reported, "total_tokens", None),
            provider_request_id=getattr(response, "_request_id", None),
            secret=self._secret,
        )

    def _transcription_usage(self, response: object, target: Target) -> UsageEntry:
        reported = getattr(response, "usage", None)
        usage_type = getattr(reported, "type", None)
        tokens = usage_type == "tokens"
        return UsageEntry.from_reported(
            target.operation,
            target.model,
            input_tokens=getattr(reported, "input_tokens", None) if tokens else None,
            output_tokens=getattr(reported, "output_tokens", None) if tokens else None,
            total_tokens=getattr(reported, "total_tokens", None) if tokens else None,
            audio_seconds=getattr(reported, "seconds", None) if usage_type == "duration" else None,
            provider_request_id=getattr(response, "_request_id", None),
            secret=self._secret,
        )

    async def _chat(self, target: Target, messages: list, max_tokens: int, temperature: float, timeout: httpx.Timeout) -> object:
        self._guard.reset()
        return await self._client.chat.completions.create(
            model=target.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            store=False,
            stream=False,
            timeout=timeout,
        )

    async def _transcribe(self, target: Target, upload: tuple, timeout: httpx.Timeout) -> object:
        self._guard.reset()
        return await self._client.audio.transcriptions.create(
            model=target.model,
            file=upload,
            response_format="json",
            timeout=timeout,
        )

    # -- ProviderSession -----------------------------------------------------------

    async def generate_text(self, target: Target, text: str, remaining_seconds: float) -> StepOutput:
        target = self._check_target(target, Operation.GENERATE_TEXT)
        if not isinstance(text, str) or not text:
            raise ProviderIntegrationError(ErrorCode.INVALID_INPUT)
        timeout = self._timeout(remaining_seconds)
        settings = self._config.generation
        messages = [
            {"role": "system", "content": settings.system_prompt},
            {"role": "user", "content": text},
        ]
        try:
            response = await self._chat(target, messages, settings.max_tokens, settings.temperature, timeout)
        except Exception as exc:
            raise ProviderOperationError(self._code(exc), self._failure_usage(exc, target)) from None
        usage = self._chat_usage(response, target)
        content = _first_message_content(response)
        if content is None:
            raise ProviderOperationError(ErrorCode.PROVIDER_RESPONSE_INVALID, usage)
        return StepOutput(content, usage)

    async def transcribe_audio(
        self, target: Target, audio: bytes, audio_format: AudioFormat, remaining_seconds: float
    ) -> StepOutput:
        target = self._check_target(target, Operation.TRANSCRIBE_AUDIO)
        if type(audio) is not bytes or not audio or not isinstance(audio_format, AudioFormat):
            raise ProviderIntegrationError(ErrorCode.INVALID_INPUT)
        timeout = self._timeout(remaining_seconds)
        upload = (f"input.{audio_format.value}", io.BytesIO(audio))  # caller filenames are never used (L4)
        try:
            response = await self._transcribe(target, upload, timeout)
        except Exception as exc:
            raise ProviderOperationError(self._code(exc), self._failure_usage(exc, target)) from None
        usage = self._transcription_usage(response, target)
        transcript = getattr(response, "text", None)
        if not isinstance(transcript, str):
            raise ProviderOperationError(ErrorCode.PROVIDER_RESPONSE_INVALID, usage)
        return StepOutput(transcript, usage)

    async def validate_access(self, target: Target, remaining_seconds: float) -> ProbeOutcome:
        """Exactly one fixed synthetic probe for ``target`` (L6, B5/B6); never customer content."""
        target = self._check_target(target)
        timeout = self._timeout(remaining_seconds)
        try:
            if target.operation is Operation.GENERATE_TEXT:
                response = await self._chat(
                    target, [{"role": "user", "content": TEXT_PROBE_PROMPT}], TEXT_PROBE_MAX_TOKENS, 0, timeout
                )
            else:
                upload = (AUDIO_PROBE_FILENAME, io.BytesIO(build_silent_wav()))
                response = await self._transcribe(target, upload, timeout)
        except Exception as exc:
            code = self._code(exc)
            status = ValidationStatus.REJECTED if code in _REJECTION_CODES else ValidationStatus.INDETERMINATE
            return ProbeOutcome(status, code, self._failure_usage(exc, target))

        if target.operation is Operation.GENERATE_TEXT:
            usage = self._chat_usage(response, target)
            content = _first_message_content(response)
            proven = isinstance(content, str) and bool(content.strip())
        else:
            usage = self._transcription_usage(response, target)
            proven = isinstance(getattr(response, "text", None), str)  # empty transcript is valid
        if proven:
            return ProbeOutcome(ValidationStatus.VALID, None, usage)
        return ProbeOutcome(ValidationStatus.INDETERMINATE, ErrorCode.PROVIDER_RESPONSE_INVALID, usage)


def _first_message_content(response: object) -> Optional[str]:
    """Text of the first choice; ``""`` for no content (refusal); ``None`` if malformed."""
    choices = getattr(response, "choices", None)
    if not isinstance(choices, list) or not choices:
        return None
    message = getattr(choices[0], "message", None)
    if message is None:
        return None
    content = getattr(message, "content", None)
    if content is None:
        return ""
    return content if isinstance(content, str) else None


# --- adapter ---------------------------------------------------------------------


class OpenAIAdapter:
    """ProviderAdapter for OpenAI Chat Completions and audio transcriptions (L6)."""

    def __init__(
        self,
        targets: FrozenSet[Target],
        *,
        connect_timeout_seconds: float,
        max_response_bytes: int,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        if (
            not isinstance(targets, frozenset)
            or not targets
            or not all(isinstance(t, Target) and t.operation in IMPLEMENTED_OPERATIONS for t in targets)
        ):
            raise ValueError("targets must be a nonempty frozenset of implemented Target pairs")
        if (
            type(connect_timeout_seconds) not in (int, float)
            or not math.isfinite(connect_timeout_seconds)
            or connect_timeout_seconds <= 0
        ):
            raise ValueError("connect_timeout_seconds must be a positive finite number")
        if type(max_response_bytes) is not int or max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be a positive int")
        if transport is not None and not isinstance(transport, httpx.AsyncBaseTransport):
            raise TypeError("transport must be an httpx.AsyncBaseTransport")
        self._targets = targets
        self._connect_timeout = float(connect_timeout_seconds)
        self._max_response_bytes = max_response_bytes
        self._transport = transport

    def supported_operations(self) -> FrozenSet[Target]:
        return self._targets

    def open_session(
        self, lease: CredentialLease, config: ProviderConfig
    ) -> contextlib.AbstractAsyncContextManager[OpenAISession]:
        return self._session(lease, config)

    def _inner_transport(self) -> httpx.AsyncBaseTransport:
        if self._transport is not None:
            return self._transport  # A5: tests only
        return httpx.AsyncHTTPTransport(verify=True, trust_env=False, retries=0)

    @contextlib.asynccontextmanager
    async def _session(self, lease: CredentialLease, config: ProviderConfig) -> AsyncIterator[OpenAISession]:
        if (
            not isinstance(lease, CredentialLease)
            or not isinstance(config, ProviderConfig)
            or config.provider != PROVIDER
            or lease.binding.provider != PROVIDER
        ):
            raise ProviderIntegrationError(ErrorCode.NOT_CONFIGURED)
        if _verbose_logging_enabled():
            raise ProviderIntegrationError(ErrorCode.NOT_CONFIGURED)  # A3: debug logs would carry content

        guard = GuardedTransport(self._inner_transport(), config.destination, self._max_response_bytes)
        http_client = httpx.AsyncClient(
            transport=guard,
            trust_env=False,
            follow_redirects=False,
            verify=True,
            timeout=httpx.Timeout(None, connect=self._connect_timeout),
        )
        try:
            try:
                client = AsyncOpenAI(
                    api_key=lease.secret.reveal_for_session(),
                    base_url=config.destination,
                    max_retries=0,
                    http_client=http_client,
                )
            except Exception:
                raise ProviderIntegrationError(ErrorCode.INTERNAL_ERROR) from None
            # A4: AsyncOpenAI reads OPENAI_ORG_ID / OPENAI_PROJECT_ID when these are None at
            # construction; clear them so no organization/project header is ever sent.
            client.organization = None
            client.project = None
            try:
                yield OpenAISession(client, lease, config, self._targets, self._connect_timeout, guard)
            finally:
                await client.close()
        finally:
            await http_client.aclose()
