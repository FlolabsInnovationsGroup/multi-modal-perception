# Temporary local result types. Will be replaced by shared types from ports.py after T2.1.
import io
import wave
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from openai import AsyncOpenAI

DEFAULT_BASE_URL = "https://api.openai.com/v1/"
DEFAULT_SYSTEM_PROMPT = (
    "You are a fast, concise multimodal perception assistant. "
    "Given text input that may describe visual, audio, or sensor context, "
    "return a short, actionable analysis focused on what matters operationally."
)


@dataclass
class LocalGenerationResult:
    ok: bool
    result: Optional[str] = None
    model: Optional[str] = None
    provider_request_id: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class LocalTranscriptionResult:
    ok: bool
    result: Optional[str] = None
    model: Optional[str] = None
    provider_request_id: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class LocalValidationResult:
    ok: bool
    status: str
    message: Optional[str] = None
    model: Optional[str] = None
    provider_request_id: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None


class OpenAIAdapter:
    """OpenAI adapter for the provider-integration local contract."""

    DEFAULT_MODEL = "gpt-4o-mini"
    DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"
    DEFAULT_TIMEOUT_SECONDS = 30.0
    DEFAULT_MAX_RETRIES = 0

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_url: str = DEFAULT_BASE_URL,
        client_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("api_key must be a non-empty string")

        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_url = base_url
        self._client_factory = client_factory or self._default_client_factory
        self._client = self._client_factory(
            api_key=self.api_key,
            base_url=self.base_url,
            max_retries=self.max_retries,
            timeout=self.timeout,
        )

    def supported_operations(self) -> tuple[str, ...]:
        return ("generate_text", "transcribe_audio", "validate_access")

    def _default_client_factory(
        self,
        *,
        api_key: str,
        base_url: str,
        max_retries: int,
        timeout: float,
    ) -> Any:
        return AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=max_retries,
            timeout=timeout,
        )

    async def generate_text(
        self,
        *,
        model: str = DEFAULT_MODEL,
        text: str,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_tokens: int = 256,
        temperature: float = 0.4,
        store: bool = False,
    ) -> LocalGenerationResult:
        if not text:
            return LocalGenerationResult(ok=False, result="", model=model, error="INVALID_INPUT")

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "store": store,
        }

        try:
            response = await self._client.chat.completions.create(**payload)
            content = getattr(getattr(response, "choices", [None])[0], "message", None)
            text_value = getattr(content, "content", "") or ""
            provider_request_id = getattr(response, "id", None)
            usage = self._normalize_usage(getattr(response, "usage", None))
            return LocalGenerationResult(
                ok=True,
                result=str(text_value).strip(),
                model=model,
                provider_request_id=provider_request_id,
                usage=usage,
            )
        except Exception as exc:  # pragma: no cover - mapping exercised by tests
            mapped = self._map_exception(exc)
            return LocalGenerationResult(
                ok=False,
                result=None,
                model=model,
                provider_request_id=None,
                error=mapped,
            )

    async def transcribe_audio(
        self,
        *,
        model: str = DEFAULT_TRANSCRIPTION_MODEL,
        audio_bytes: bytes,
        filename: str = "validation.wav",
        response_format: str = "json",
    ) -> LocalTranscriptionResult:
        if not audio_bytes:
            return LocalTranscriptionResult(ok=False, result="", model=model, error="INVALID_INPUT")

        audio_stream = io.BytesIO(audio_bytes)
        audio_stream.name = filename

        try:
            response = await self._client.audio.transcriptions.create(
                model=model,
                file=audio_stream,
                response_format=response_format,
            )
            transcript_text = getattr(response, "text", "") or ""
            provider_request_id = getattr(response, "id", None)
            usage = self._normalize_usage(getattr(response, "usage", None))
            return LocalTranscriptionResult(
                ok=True,
                result=str(transcript_text),
                model=model,
                provider_request_id=provider_request_id,
                usage=usage,
            )
        except Exception as exc:  # pragma: no cover - mapping exercised by tests
            mapped = self._map_exception(exc)
            return LocalTranscriptionResult(
                ok=False,
                result=None,
                model=model,
                provider_request_id=None,
                error=mapped,
            )

    async def validate_access(
        self,
        context: Any,
        credential: str,
        model: str,
        operation: str,
    ) -> LocalValidationResult:
        if not credential or not credential.strip():
            return LocalValidationResult(ok=False, status="CREDENTIAL_UNAVAILABLE", message="Missing credential")

        if context is None:
            return LocalValidationResult(ok=False, status="ACCESS_DENIED", message="Untrusted context")

        if operation in {"generate_text", "text", "text_generation"}:
            return await self._validate_text_capability(model=model)

        if operation in {"transcribe_audio", "audio", "audio_transcription"}:
            return await self._validate_audio_capability(model=model)

        return LocalValidationResult(ok=False, status="UNSUPPORTED_OPERATION", message="Unsupported operation")

    async def _validate_text_capability(self, *, model: str) -> LocalValidationResult:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "max_tokens": 8,
            "temperature": 0,
            "store": False,
        }
        try:
            response = await self._client.chat.completions.create(**payload)
            content = getattr(getattr(response, "choices", [None])[0], "message", None)
            text_value = getattr(content, "content", "") or ""
            provider_request_id = getattr(response, "id", None)
            if str(text_value).strip():
                return LocalValidationResult(
                    ok=True,
                    status="VALID",
                    message="Text validation successful",
                    model=model,
                    provider_request_id=provider_request_id,
                )
            return LocalValidationResult(
                ok=True,
                status="VALID",
                message="Text validation returned an empty but structurally valid response",
                model=model,
                provider_request_id=provider_request_id,
            )
        except Exception as exc:  # pragma: no cover - exercised in tests
            return LocalValidationResult(
                ok=False,
                status=self._map_exception(exc),
                message="Text validation failed",
                model=model,
            )

    async def _validate_audio_capability(self, *, model: str) -> LocalValidationResult:
        audio_bytes = _build_silent_wav_bytes(duration_seconds=1.0, sample_rate=16000)
        audio_stream = io.BytesIO(audio_bytes)
        audio_stream.name = "validation.wav"
        try:
            response = await self._client.audio.transcriptions.create(
                model=model,
                file=audio_stream,
                response_format="json",
            )
            transcript_text = getattr(response, "text", "")
            provider_request_id = getattr(response, "id", None)
            if hasattr(response, "text"):
                return LocalValidationResult(
                    ok=True,
                    status="VALID",
                    message="Audio validation successful",
                    model=model,
                    provider_request_id=provider_request_id,
                )
            return LocalValidationResult(
                ok=True,
                status="VALID",
                message="Audio validation returned a success object",
                model=model,
                provider_request_id=provider_request_id,
            )
        except Exception as exc:  # pragma: no cover - exercised in tests
            return LocalValidationResult(
                ok=False,
                status=self._map_exception(exc),
                message="Audio validation failed",
                model=model,
            )

    def _normalize_usage(self, usage: Any) -> Optional[Dict[str, Any]]:
        if usage is None:
            return None
        if isinstance(usage, dict):
            return dict(usage)
        result: Dict[str, Any] = {}
        for field in ("prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens"):
            value = getattr(usage, field, None)
            if value is not None:
                result[field] = value
        return result or None

    def _map_exception(self, exc: Exception) -> str:
        status_code = getattr(exc, "status_code", None)
        error_code = getattr(exc, "code", None) or getattr(exc, "error", None)
        if isinstance(error_code, dict):
            error_code = error_code.get("code")
        error_code = str(error_code) if error_code is not None else None

        if status_code == 401 and error_code in {"invalid_api_key", "authentication_failed"}:
            return "CREDENTIAL_REJECTED"
        if status_code == 401:
            return "ACCESS_DENIED"
        if status_code == 403:
            return "CAPABILITY_DENIED"
        if status_code == 404 and error_code in {"model_not_found", "not_found"}:
            return "CAPABILITY_DENIED"
        if status_code == 429:
            if error_code in {
                "insufficient_quota",
                "credit_balance_exhausted",
                "organization_spend_limit_exceeded",
                "project_spend_limit_exceeded",
                "organization_usage_limit_exceeded",
            }:
                return "QUOTA_EXCEEDED"
            return "RATE_LIMITED"
        if status_code in {408, 500, 502, 503, 504}:
            return "PROVIDER_UNAVAILABLE"
        if status_code in {400, 413, 422}:
            return "INVALID_INPUT"
        if status_code is not None:
            return "PROVIDER_RESPONSE_INVALID"
        return "INTERNAL_ERROR"


def _build_silent_wav_bytes(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    frame_count = int(sample_rate * duration_seconds)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count)
    return buffer.getvalue()
