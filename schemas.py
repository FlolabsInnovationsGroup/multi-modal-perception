from pydantic import BaseModel
from typing import Literal


class PerceptionInput(BaseModel):
    """Expected request body for /process."""

    text_input: str
    audio_input: str


class PerceptionOutput(BaseModel):
    """Expected response body from /process."""

    result: str
    model: str
    file_type: Literal["text", "audio", "image", "video"]


class TranscriptionOutput(BaseModel):
    """Response from the /transcribe endpoint."""

    transcript: str
    model: str
