"""
Multimodal Perception Microservice — main orchestration and API.

Perception routes accept text and audio as form data.
Standalone speech routes accept raw recordings or JSON text.
"""
from fastapi import FastAPI
import logging

from dotenv import load_dotenv

from api import health, openAI, process, speech

logging.basicConfig(level=logging.INFO)

load_dotenv()

app = FastAPI(
    title="Multimodal Perception Microservice",
    description="Foundation for multimodal perception system",
    version="0.1.0"
)

app.include_router(health.router, tags=["System"])
app.include_router(process.router, tags=["Perception"])
app.include_router(openAI.router, tags=["OpenAI"])
app.include_router(speech.router, tags=["Speech"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
