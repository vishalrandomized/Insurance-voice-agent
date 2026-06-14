from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime
from typing import Any
from uuid import UUID

from .base import Repository, Row
from .errors import ConflictError


class InMemoryRepository(Repository):
    def __init__(self) -> None:
        self.sessions: dict[UUID, Row] = {}
        self.leads: dict[UUID, Row] = {}
        self.callback_actions: dict[UUID, Row] = {}
        self.audit_events: dict[UUID, Row] = {}
        self._audit_keys: dict[str, UUID] = {}
        self._lock = asyncio.Lock()

    async def create_session_with_lead(
        self,
        *,
        session_id: UUID,
        lead_id: UUID,
        product_id: UUID,
        customer_name: str | None,
        phone: str | None,
        now: datetime,
    ) -> tuple[Row, Row]:
        session = {
            "id": session_id,
            "product_id": product_id,
            "status": "active",
            "started_at": now,
            "ended_at": None,
        }
        lead = {
            "id": lead_id,
            "session_id": session_id,
            "customer_name": customer_name,
            "phone": phone,
            "product_id": product_id,
            "callback_status": "not_requested",
            "callback_reason": None,
            "preferred_callback_text": None,
            "preferred_callback_at": None,
            "conversation_summary": None,
            "created_at": now,
            "updated_at": now,
        }
        async with self._lock:
            if session_id in self.sessions or lead_id in self.leads:
                raise ConflictError("Session or lead already exists")
            self.sessions[session_id] = session
            self.leads[lead_id] = lead
        return deepcopy(session), deepcopy(lead)

    async def end_session(
        self, session_id: UUID, *, status: str, ended_at: datetime
    ) -> Row:
        async with self._lock:
            session = self.sessions.get(session_id)
            if session is None:
                return {}
            if session["status"] == "active":
                session.update(status=status, ended_at=ended_at)
            return deepcopy(session)

    async def get_session(self, session_id: UUID) -> Row | None:
        row = self.sessions.get(session_id)
        return deepcopy(row) if row else None

    async def get_lead(self, lead_id: UUID) -> Row | None:
        row = self.leads.get(lead_id)
        return deepcopy(row) if row else None

    async def get_lead_by_session(self, session_id: UUID) -> Row | None:
        for lead in self.leads.values():
            if lead["session_id"] == session_id:
                return deepcopy(lead)
        return None

    async def list_leads(self, *, callback_status: str | None = None) -> list[Row]:
        rows = [
            deepcopy(row)
            for row in self.leads.values()
            if callback_status is None or row["callback_status"] == callback_status
        ]
        return sorted(rows, key=lambda row: row["updated_at"], reverse=True)

    async def update_lead(self, lead_id: UUID, values: Row) -> Row | None:
        async with self._lock:
            lead = self.leads.get(lead_id)
            if lead is None:
                return None
            lead.update(values)
            return deepcopy(lead)

    async def create_callback_action(self, action: Row) -> Row:
        action_id = _uuid(action["id"])
        async with self._lock:
            if action_id in self.callback_actions:
                raise ConflictError("Callback action already exists")
            self.callback_actions[action_id] = deepcopy(action)
        return deepcopy(action)

    async def get_callback_action(self, action_id: UUID) -> Row | None:
        row = self.callback_actions.get(action_id)
        return deepcopy(row) if row else None

    async def transition_callback_action(
        self, action_id: UUID, *, from_status: str, to_status: str
    ) -> Row | None:
        async with self._lock:
            action = self.callback_actions.get(action_id)
            if action is None or action["status"] != from_status:
                return None
            action["status"] = to_status
            return deepcopy(action)

    async def create_audit_event(self, event: Row) -> Row:
        event_id = _uuid(event["id"])
        key = event.get("idempotency_key")
        async with self._lock:
            if key and key in self._audit_keys:
                existing = self.audit_events[self._audit_keys[key]]
                return deepcopy(existing)
            self.audit_events[event_id] = deepcopy(event)
            if key:
                self._audit_keys[key] = event_id
        return deepcopy(event)

    async def get_audit_event_by_idempotency_key(self, key: str) -> Row | None:
        event_id = self._audit_keys.get(key)
        row = self.audit_events.get(event_id) if event_id else None
        return deepcopy(row) if row else None

    async def list_audit_events(self, lead_id: UUID) -> list[Row]:
        rows = [
            deepcopy(row)
            for row in self.audit_events.values()
            if row["lead_id"] == lead_id
        ]
        return sorted(rows, key=lambda row: row["created_at"], reverse=True)

    async def healthcheck(self) -> bool:
        return True


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))
