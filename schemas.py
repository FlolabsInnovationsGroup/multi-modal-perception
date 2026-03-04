from pydantic import BaseModel


class PerceptionInput(BaseModel):
    """Expected request body for /process."""

    text_input: str


class PerceptionOutput(BaseModel):
    """Expected response body from /process."""

    result: str
