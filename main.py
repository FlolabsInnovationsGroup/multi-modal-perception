"""
Multimodal Perception Microservice — main orchestration and API.

Trigger: FastAPI POST /process with JSON body.
Input/Output: Text (Pydantic models) for now; extensible for future multimodal (vLLM, etc.).
"""
from fastapi import FastAPI
import logging

from dotenv import load_dotenv

from api import health, openAI, process
from api.service_auth import ServiceKeyMiddleware

logging.basicConfig(level=logging.INFO)

load_dotenv()

app = FastAPI(
    title="Multimodal Perception Microservice",
    description="Foundation for multimodal perception system",
    version="0.1.0"
)

# Short-term guard: every route except /health needs the backend's MULTIMODAL_API_KEY.
app.add_middleware(ServiceKeyMiddleware)

app.include_router(health.router, tags=["System"])
app.include_router(process.router, tags=["Perception"])
app.include_router(openAI.router, tags=["OpenAI"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
