from pydantic import BaseModel
from fastapi import UploadFile


class PerceptionInput(BaseModel):
    """Expected request body for /process, /openAI, /process_qwen."""
    text_input: str

    # existing audio_input (for /process) – you can keep this for backward compat
    audio_input: str | None = None

    # new fields for /process_qwen (file uploads)
    image_file: UploadFile | None = None
    audio_file: UploadFile | None = None


class PerceptionOutput(BaseModel):
    """Expected response body."""
    result: str