from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from app.db.base import Repository
from app.db.errors import NotFoundError, ValidationError
from app.db.supabase import SupabaseRestRepository
from app.models.schemas import Lead, SessionCreate, SessionCreated


LOCAL_DEMO_PRODUCT_ID = uuid5(NAMESPACE_URL, "insurance-agent:local-demo-product")


class SessionService:
    def __init__(self, repository: Repository):
        self.repository = repository

    async def create_session(self, request: SessionCreate) -> SessionCreated:
        product_id = request.product_id or self._default_product_id()
        session_id = uuid4()
        lead_id = uuid4()
        now = datetime.now(UTC)
        _, lead_row = await self.repository.create_session_with_lead(
            session_id=session_id,
            lead_id=lead_id,
            product_id=product_id,
            customer_name=_clean_optional(request.customer_name),
            phone=_clean_optional(request.phone),
            now=now,
        )
        return SessionCreated(
            session_id=session_id,
            lead=Lead.model_validate(lead_row),
            websocket_url=self._websocket_url(session_id),
        )

    async def end_session(
        self, session_id: UUID, *, abandoned: bool = False
    ) -> dict[str, object]:
        status = "abandoned" if abandoned else "completed"
        row = await self.repository.end_session(
            session_id, status=status, ended_at=datetime.now(UTC)
        )
        if not row:
            raise NotFoundError("Session not found")
        return row

    async def get_session(self, session_id: UUID) -> dict[str, object]:
        row = await self.repository.get_session(session_id)
        if row is None:
            raise NotFoundError("Session not found")
        return row

    def _default_product_id(self) -> UUID:
        configured = os.getenv("DEFAULT_PRODUCT_ID", "").strip()
        if configured:
            try:
                return UUID(configured)
            except ValueError as exc:
                raise ValidationError("DEFAULT_PRODUCT_ID must be a UUID") from exc
        if isinstance(self.repository, SupabaseRestRepository):
            raise ValidationError(
                "product_id is required when Supabase persistence is enabled"
            )
        return LOCAL_DEMO_PRODUCT_ID

    @staticmethod
    def _websocket_url(session_id: UUID) -> str:
        base = (
            os.getenv("PUBLIC_WS_URL")
            or os.getenv("WS_BASE_URL")
            or "ws://localhost:8000"
        ).rstrip("/")
        return f"{base}/ws/voice/{session_id}"


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
