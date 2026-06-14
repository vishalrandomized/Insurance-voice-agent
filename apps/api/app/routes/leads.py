from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.db.errors import RepositoryError
from app.models.schemas import AuditEvent, CallbackStatus, CallbackUpdate, Lead
from app.services.leads import LeadService
from .dependencies import lead_service_dependency
from .errors import as_http_exception

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=list[Lead])
async def list_leads(
    callback_status: CallbackStatus | None = Query(default=None),
    service: LeadService = Depends(lead_service_dependency),
) -> list[Lead]:
    try:
        return await service.list_leads(callback_status)
    except RepositoryError as exc:
        raise as_http_exception(exc) from exc


@router.get("/{lead_id}", response_model=Lead)
async def get_lead(
    lead_id: UUID,
    service: LeadService = Depends(lead_service_dependency),
) -> Lead:
    try:
        return await service.get_lead(lead_id)
    except RepositoryError as exc:
        raise as_http_exception(exc) from exc


@router.patch("/{lead_id}/callback", response_model=Lead)
async def update_callback(
    lead_id: UUID,
    request: CallbackUpdate,
    service: LeadService = Depends(lead_service_dependency),
) -> Lead:
    try:
        return await service.update_callback(lead_id, request)
    except RepositoryError as exc:
        raise as_http_exception(exc) from exc


@router.get("/{lead_id}/audit-events", response_model=list[AuditEvent])
async def list_audit_events(
    lead_id: UUID,
    service: LeadService = Depends(lead_service_dependency),
) -> list[AuditEvent]:
    try:
        return await service.list_audit_events(lead_id)
    except RepositoryError as exc:
        raise as_http_exception(exc) from exc
