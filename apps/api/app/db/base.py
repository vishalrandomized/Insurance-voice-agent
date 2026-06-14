from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from uuid import UUID


Row = dict[str, Any]


class Repository(ABC):
    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    async def end_session(
        self, session_id: UUID, *, status: str, ended_at: datetime
    ) -> Row:
        raise NotImplementedError

    @abstractmethod
    async def get_session(self, session_id: UUID) -> Row | None:
        raise NotImplementedError

    @abstractmethod
    async def get_lead(self, lead_id: UUID) -> Row | None:
        raise NotImplementedError

    @abstractmethod
    async def get_lead_by_session(self, session_id: UUID) -> Row | None:
        raise NotImplementedError

    @abstractmethod
    async def list_leads(self, *, callback_status: str | None = None) -> list[Row]:
        raise NotImplementedError

    @abstractmethod
    async def update_lead(self, lead_id: UUID, values: Row) -> Row | None:
        raise NotImplementedError

    @abstractmethod
    async def create_callback_action(self, action: Row) -> Row:
        raise NotImplementedError

    @abstractmethod
    async def get_callback_action(self, action_id: UUID) -> Row | None:
        raise NotImplementedError

    @abstractmethod
    async def transition_callback_action(
        self, action_id: UUID, *, from_status: str, to_status: str
    ) -> Row | None:
        raise NotImplementedError

    @abstractmethod
    async def create_audit_event(self, event: Row) -> Row:
        raise NotImplementedError

    @abstractmethod
    async def get_audit_event_by_idempotency_key(self, key: str) -> Row | None:
        raise NotImplementedError

    @abstractmethod
    async def list_audit_events(self, lead_id: UUID) -> list[Row]:
        raise NotImplementedError

    @abstractmethod
    async def healthcheck(self) -> bool:
        raise NotImplementedError
