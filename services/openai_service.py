import asyncio
import io
import logging
import os
import time
from typing import Dict, Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "256"))
TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.4"))

SYSTEM_PROMPT = os.getenv(
    "OPENAI_SYSTEM_PROMPT",
    (
        "You are a fast, concise multimodal perception assistant. "
        "Given text input that may describe visual, audio, or sensor context, "
        "return a short, actionable analysis focused on what matters operationally."
    ),
)


class UltraFastOpenAIService:

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY environment variable is required for OpenAI integration."
            )

        self._client = AsyncOpenAI(api_key=api_key)
        self._cache: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def generate_response(self, user_message: str) -> str:
        normalized = user_message.strip()
        if not normalized:
            return ""

        cache_key = normalized.lower()
        start = time.monotonic()

        cached = self._cache.get(cache_key)
        if cached is not None:
            elapsed_ms = (time.monotonic() - start) * 1000
            return cached

        try:
            response = await self._client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": normalized},
                ],
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
            )

            content = (response.choices[0].message.content or "").strip()

            async with self._lock:
                self._cache[cache_key] = content

            elapsed_ms = (time.monotonic() - start) * 1000

            return content

        except Exception as exc:  # noqa: BLE001
            elapsed_ms = (time.monotonic() - start) * 1000
            return f"Perception system temporarily unavailable. Echoing input: {normalized}"

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
    ) -> str:
        if not audio_bytes:
            return ""

        audio_stream = io.BytesIO(audio_bytes)
        audio_stream.name = filename

        transcript = await self._client.audio.transcriptions.create(
            model=TRANSCRIBE_MODEL,
            file=audio_stream,
        )
        return (transcript.text or "").strip()

    async def generate_multimodal_response(
        self,
        text_input: str,
        audio_bytes: bytes,
        audio_filename: str = "audio.wav",
    ) -> str:
        normalized_text = (text_input or "").strip()
        transcript = await self.transcribe_audio(audio_bytes, audio_filename)

        if normalized_text and transcript:
            user_message = (
                f"{normalized_text}\n\n"
                f"Audio transcript:\n{transcript}"
            )
        elif transcript:
            user_message = transcript
        else:
            user_message = normalized_text

        return await self.generate_response(user_message)


_ultra_fast_service: Optional[UltraFastOpenAIService] = None


def get_ultra_fast_service() -> UltraFastOpenAIService:
    """
    Lazily-initialized singleton to avoid recreating the client per-request.
    """
    global _ultra_fast_service

    if _ultra_fast_service is None:
        _ultra_fast_service = UltraFastOpenAIService()

    return _ultra_fast_service

