from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.db.base import Repository, Row
from app.db.errors import ConflictError, NotFoundError, ValidationError
from app.models.schemas import (
    CallbackAction,
    CallbackActionCreate,
    CallbackStatus,
    Lead,
)

from app.services.leads import LeadService


class CallbackService:
    _locks: defaultdict[UUID, asyncio.Lock] = defaultdict(asyncio.Lock)

    def __init__(self, repository: Repository):
        self.repository = repository
        self.leads = LeadService(repository)

    async def create_action(
        self, lead_id: UUID, request: CallbackActionCreate
    ) -> CallbackAction:
        await self.leads.get_lead(lead_id)
        reason = request.reason.strip()
        if not reason:
            raise ValidationError("Callback reason is required")
        action_id = uuid4()
        now = datetime.now(UTC)
        row = {
            "id": action_id,
            "lead_id": lead_id,
            "status": "pending",
            "reason": reason,
            "preferred_callback_text": _clean_optional(
                request.preferred_callback_text
            ),
            "source": request.source.value,
            "idempotency_key": f"callback:{lead_id}:{action_id}",
            "expires_at": now + timedelta(seconds=60),
            "created_at": now,
        }
        created = await self.repository.create_callback_action(row)
        return CallbackAction.model_validate(created)

    async def confirm_action(self, action_id: UUID) -> Lead:
        async with self._locks[action_id]:
            action = await self._get_action(action_id)
            key = self._commit_key(action)
            existing_event = (
                await self.repository.get_audit_event_by_idempotency_key(key)
            )
            if existing_event:
                return await self.leads.get_lead(UUID(str(action["lead_id"])))

            action = await self._expire_if_needed(action)
            if action["status"] == "expired":
                raise ConflictError("Callback action has expired")
            if action["status"] == "cancelled":
                raise ConflictError("Callback action was cancelled")
            if action["status"] == "pending":
                transitioned = await self.repository.transition_callback_action(
                    action_id, from_status="pending", to_status="confirmed"
                )
                if transitioned is None:
                    action = await self._get_action(action_id)
                    if action["status"] != "confirmed":
                        raise ConflictError(
                            f"Callback action is already {action['status']}"
                        )
                else:
                    action = transitioned

            lead_id = UUID(str(action["lead_id"]))
            now = datetime.now(UTC)
            lead_row = await self.repository.update_lead(
                lead_id,
                {
                    "callback_status": CallbackStatus.REQUESTED.value,
                    "callback_reason": action["reason"],
                    "preferred_callback_text": action.get(
                        "preferred_callback_text"
                    ),
                    "preferred_callback_at": None,
                    "updated_at": now,
                },
            )
            if lead_row is None:
                raise NotFoundError("Lead not found")
            await self.repository.create_audit_event(
                {
                    "id": uuid4(),
                    "lead_id": lead_id,
                    "event_type": "callback_requested",
                    "source": action["source"],
                    "payload": {
                        "action_id": str(action_id),
                        "reason": action["reason"],
                        "preferred_callback_text": action.get(
                            "preferred_callback_text"
                        ),
                        "status": CallbackStatus.REQUESTED.value,
                    },
                    "idempotency_key": key,
                    "created_at": now,
                }
            )
            return Lead.model_validate(lead_row)

    async def cancel_action(self, action_id: UUID) -> CallbackAction:
        async with self._locks[action_id]:
            action = await self._get_action(action_id)
            action = await self._expire_if_needed(action)
            if action["status"] == "confirmed":
                raise ConflictError("Confirmed callback actions cannot be cancelled")
            if action["status"] in {"cancelled", "expired"}:
                return CallbackAction.model_validate(action)
            transitioned = await self.repository.transition_callback_action(
                action_id, from_status="pending", to_status="cancelled"
            )
            if transitioned is None:
                transitioned = await self._get_action(action_id)
            return CallbackAction.model_validate(transitioned)

    async def _get_action(self, action_id: UUID) -> Row:
        row = await self.repository.get_callback_action(action_id)
        if row is None:
            raise NotFoundError("Callback action not found")
        return row

    async def _expire_if_needed(self, action: Row) -> Row:
        expires_at = _datetime(action["expires_at"])
        if action["status"] == "pending" and expires_at <= datetime.now(UTC):
            transitioned = await self.repository.transition_callback_action(
                UUID(str(action["id"])),
                from_status="pending",
                to_status="expired",
            )
            if transitioned:
                return transitioned
        return action

    @staticmethod
    def _commit_key(action: Row) -> str:
        return f"{action['idempotency_key']}:confirm"


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
