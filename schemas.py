from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints


class TranscriptionOutput(BaseModel):
    text: str


class SynthesisInput(BaseModel):
    text: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4096)
    ]


class PerceptionInput(BaseModel):
    """Expected request body for /process."""

    text_input: str
    audio_input: str


class PerceptionOutput(BaseModel):
    """Expected response body from /process."""

    result: str
    model: str
    file_type: Literal["text", "audio", "image", "video"]
