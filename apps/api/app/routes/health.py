from fastapi import APIRouter, Depends, Response, status

from app.db import Repository
from .dependencies import repository_dependency

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(
    response: Response,
    repository: Repository = Depends(repository_dependency),
) -> dict[str, str]:
    healthy = await repository.healthcheck()
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if healthy else "degraded",
        "persistence": type(repository).__name__,
    }
