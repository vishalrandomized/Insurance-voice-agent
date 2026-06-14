from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.db.base import Repository
from app.db.errors import NotFoundError, ValidationError
from app.models.schemas import (
    AuditEvent,
    CallbackStatus,
    CallbackUpdate,
    Lead,
)


class LeadService:
    def __init__(self, repository: Repository):
        self.repository = repository

    async def list_leads(
        self, callback_status: CallbackStatus | None = None
    ) -> list[Lead]:
        rows = await self.repository.list_leads(
            callback_status=callback_status.value if callback_status else None
        )
        return [Lead.model_validate(row) for row in rows]

    async def get_lead(self, lead_id: UUID) -> Lead:
        row = await self.repository.get_lead(lead_id)
        if row is None:
            raise NotFoundError("Lead not found")
        return Lead.model_validate(row)

    async def get_lead_for_session(self, session_id: UUID) -> Lead:
        row = await self.repository.get_lead_by_session(session_id)
        if row is None:
            raise NotFoundError("Lead not found for session")
        return Lead.model_validate(row)

    async def update_callback(
        self, lead_id: UUID, update: CallbackUpdate
    ) -> Lead:
        current = await self.get_lead(lead_id)
        self._validate_transition(
            current.callback_status, update.status, update.source.value
        )
        now = datetime.now(UTC)
        row = await self.repository.update_lead(
            lead_id,
            {
                "callback_status": update.status.value,
                "callback_reason": update.reason,
                "preferred_callback_text": update.preferred_callback_text,
                "preferred_callback_at": update.preferred_callback_at,
                "updated_at": now,
            },
        )
        if row is None:
            raise NotFoundError("Lead not found")
        await self.repository.create_audit_event(
            {
                "id": uuid4(),
                "lead_id": lead_id,
                "event_type": "callback_status_changed",
                "source": update.source.value,
                "payload": {
                    "previous_status": current.callback_status.value,
                    "status": update.status.value,
                    "reason": update.reason,
                    "preferred_callback_text": update.preferred_callback_text,
                    "preferred_callback_at": (
                        update.preferred_callback_at.isoformat()
                        if update.preferred_callback_at
                        else None
                    ),
                },
                "idempotency_key": None,
                "created_at": now,
            }
        )
        return Lead.model_validate(row)

    async def list_audit_events(self, lead_id: UUID) -> list[AuditEvent]:
        await self.get_lead(lead_id)
        rows = await self.repository.list_audit_events(lead_id)
        return [AuditEvent.model_validate(row) for row in rows]

    @staticmethod
    def _validate_transition(
        current: CallbackStatus, requested: CallbackStatus, source: str
    ) -> None:
        if current == requested:
            return
        if source != "salesperson" and requested not in {
            CallbackStatus.REQUESTED,
            CallbackStatus.CANCELLED,
        }:
            raise ValidationError(
                "Customers may only request or cancel a callback"
            )
        allowed = {
            CallbackStatus.NOT_REQUESTED: {
                CallbackStatus.REQUESTED,
                CallbackStatus.CANCELLED,
            },
            CallbackStatus.REQUESTED: {
                CallbackStatus.IN_PROGRESS,
                CallbackStatus.CANCELLED,
                CallbackStatus.COMPLETED,
            },
            CallbackStatus.IN_PROGRESS: {
                CallbackStatus.REQUESTED,
                CallbackStatus.CANCELLED,
                CallbackStatus.COMPLETED,
            },
            CallbackStatus.COMPLETED: {CallbackStatus.REQUESTED},
            CallbackStatus.CANCELLED: {CallbackStatus.REQUESTED},
        }
        if requested not in allowed[current]:
            raise ValidationError(
                f"Cannot change callback status from {current.value} "
                f"to {requested.value}"
            )
