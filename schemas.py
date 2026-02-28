from pydantic import BaseModel

class PerceptionInput(BaseModel):
    text_input: str

class PerceptionOutput(BaseModel):
    result: str
