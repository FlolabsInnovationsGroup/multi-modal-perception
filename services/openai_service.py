import asyncio
import audioop
import io
import logging
import os
import time
import wave
from typing import Dict, Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
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

    async def generate_response(self, user_message: str) -> tuple[str, int]:
        normalized = user_message.strip()
        if not normalized:
            return "", 0

        cache_key = normalized.lower()
        start = time.monotonic()

        cached = self._cache.get(cache_key)
        if cached is not None:
            elapsed_ms = (time.monotonic() - start) * 1000
            return cached, 0

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
            total_tokens = response.usage.total_tokens if response.usage else 0

            async with self._lock:
                self._cache[cache_key] = content

            elapsed_ms = (time.monotonic() - start) * 1000

            return content, total_tokens

        except Exception as exc:  # noqa: BLE001
            elapsed_ms = (time.monotonic() - start) * 1000
            return f"Perception system temporarily unavailable. Echoing input: {normalized}", 0

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
            model=os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe"),
            file=audio_stream,
        )
        return (transcript.text or "").strip()

    async def synthesize_speech(self, text: str) -> bytes:
        response = await self._client.audio.speech.create(
            model=os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
            voice=os.getenv("OPENAI_TTS_VOICE", "alloy"),
            input=text,
            response_format="wav",
        )
        return _normalize_speech_wav(response.content)

    async def generate_multimodal_response(
        self,
        text_input: str,
        audio_bytes: bytes,
        audio_filename: str = "audio.wav",
    ) -> tuple[str, int]:
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


def _normalize_speech_wav(audio: bytes) -> bytes:
    with wave.open(io.BytesIO(audio), "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        sample_rate = source.getframerate()
        frames = source.readframes(source.getnframes())

    if channels not in (1, 2) or sample_width != 2:
        raise ValueError("Expected 16-bit mono or stereo PCM from speech provider.")
    if not frames or len(frames) % (channels * sample_width):
        raise ValueError("Speech provider returned incomplete PCM frames.")
    if channels == 2:
        frames = audioop.tomono(frames, sample_width, 0.5, 0.5)
    if sample_rate != 16000:
        frames, _ = audioop.ratecv(frames, sample_width, 1, sample_rate, 16000, None)

    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        target.writeframes(frames)
    return output.getvalue()


_ultra_fast_service: Optional[UltraFastOpenAIService] = None


def get_ultra_fast_service() -> UltraFastOpenAIService:
    """
    Lazily-initialized singleton to avoid recreating the client per-request.
    """
    global _ultra_fast_service

    if _ultra_fast_service is None:
        _ultra_fast_service = UltraFastOpenAIService()

    return _ultra_fast_service

