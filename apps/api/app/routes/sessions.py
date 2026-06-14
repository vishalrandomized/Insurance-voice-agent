from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.db.errors import RepositoryError
from app.models.schemas import SessionCreate, SessionCreated
from app.services.sessions import SessionService
from .dependencies import session_service_dependency
from .errors import as_http_exception

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionEndRequest(BaseModel):
    status: Literal["completed", "abandoned"] = "completed"


@router.post("", response_model=SessionCreated, status_code=201)
async def create_session(
    request: SessionCreate,
    service: SessionService = Depends(session_service_dependency),
) -> SessionCreated:
    try:
        return await service.create_session(request)
    except RepositoryError as exc:
        raise as_http_exception(exc) from exc


@router.get("/{session_id}")
async def get_session(
    session_id: UUID,
    service: SessionService = Depends(session_service_dependency),
) -> dict[str, object]:
    try:
        return await service.get_session(session_id)
    except RepositoryError as exc:
        raise as_http_exception(exc) from exc


@router.post("/{session_id}/end")
async def end_session(
    session_id: UUID,
    request: SessionEndRequest | None = None,
    service: SessionService = Depends(session_service_dependency),
) -> dict[str, object]:
    try:
        return await service.end_session(
            session_id,
            abandoned=bool(request and request.status == "abandoned"),
        )
    except RepositoryError as exc:
        raise as_http_exception(exc) from exc
