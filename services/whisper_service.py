import os
from typing import Optional

import httpx


MINICPM_API_URL = os.getenv("MINICPM_API_URL", "").rstrip("/")


class WhisperService:
    def __init__(self) -> None:
        self._base_url = MINICPM_API_URL

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
    ) -> tuple[str, str]:
        if not audio_bytes:
            return "", "small"
        if not self._base_url:
            raise RuntimeError("MINICPM_API_URL is required for Whisper transcription.")

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self._base_url}/v1/transcribe",
                files={"audio_file": (filename, audio_bytes, "application/octet-stream")},
            )
        response.raise_for_status()

        data = response.json()
        transcript = data.get("transcript")
        model = data.get("model")
        if not isinstance(transcript, str) or not isinstance(model, str):
            raise ValueError("Whisper service returned an invalid response.")

        return transcript.strip(), model


_whisper_service: Optional[WhisperService] = None


def get_whisper_service() -> WhisperService:
    global _whisper_service

    if _whisper_service is None:
        _whisper_service = WhisperService()

    return _whisper_service
