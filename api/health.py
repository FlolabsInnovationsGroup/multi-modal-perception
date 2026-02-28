from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health_check():
    """Simple health check for Docker/Kubernetes routing."""
    return {"status": "healthy"}