from uuid import UUID

from fastapi import APIRouter, Depends

from app.db.errors import RepositoryError
from app.models.schemas import CallbackAction, CallbackActionCreate, Lead
from app.services.callbacks import CallbackService
from .dependencies import callback_service_dependency
from .errors import as_http_exception

router = APIRouter(tags=["callbacks"])


@router.post(
    "/leads/{lead_id}/callback-actions",
    response_model=CallbackAction,
    status_code=201,
)
async def create_callback_action(
    lead_id: UUID,
    request: CallbackActionCreate,
    service: CallbackService = Depends(callback_service_dependency),
) -> CallbackAction:
    try:
        return await service.create_action(lead_id, request)
    except RepositoryError as exc:
        raise as_http_exception(exc) from exc


@router.post(
    "/callback-actions/{action_id}/confirm", response_model=Lead
)
async def confirm_callback_action(
    action_id: UUID,
    service: CallbackService = Depends(callback_service_dependency),
) -> Lead:
    try:
        return await service.confirm_action(action_id)
    except RepositoryError as exc:
        raise as_http_exception(exc) from exc


@router.post(
    "/callback-actions/{action_id}/cancel",
    response_model=CallbackAction,
)
async def cancel_callback_action(
    action_id: UUID,
    service: CallbackService = Depends(callback_service_dependency),
) -> CallbackAction:
    try:
        return await service.cancel_action(action_id)
    except RepositoryError as exc:
        raise as_http_exception(exc) from exc
