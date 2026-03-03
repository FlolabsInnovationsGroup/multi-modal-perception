from fastapi import FastAPI
import logging

from api import health, process

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Multimodal Perception Microservice",
    description="Foundation for multimodal perception system",
    version="0.1.0"
)

app.include_router(health.router, tags=["System"])
app.include_router(process.router, tags=["Perception"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)