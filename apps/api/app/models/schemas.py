from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class CallbackStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    REQUESTED = "requested"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CallbackSource(StrEnum):
    CUSTOMER_VOICE = "customer_voice"
    CUSTOMER_UI = "customer_ui"
    SALESPERSON = "salesperson"


class Citation(APIModel):
    id: UUID
    document_id: UUID
    filename: str
    page_number: int
    section_heading: str | None = None
    passage: str


class Lead(APIModel):
    id: UUID
    session_id: UUID
    customer_name: str | None = None
    phone: str | None = None
    product_id: UUID
    callback_status: CallbackStatus
    callback_reason: str | None = None
    preferred_callback_text: str | None = None
    preferred_callback_at: datetime | None = None
    conversation_summary: str | None = None
    created_at: datetime
    updated_at: datetime


class CallbackUpdate(APIModel):
    status: CallbackStatus
    reason: str | None = None
    preferred_callback_text: str | None = None
    preferred_callback_at: datetime | None = None
    source: CallbackSource


class AuditEvent(APIModel):
    id: UUID
    lead_id: UUID
    event_type: str
    source: CallbackSource
    payload: dict[str, Any]
    created_at: datetime


class SessionCreate(APIModel):
    product_id: UUID | None = None
    customer_name: str | None = None
    phone: str | None = None


class SessionCreated(APIModel):
    session_id: UUID
    lead: Lead
    websocket_url: str


class CallbackActionCreate(APIModel):
    reason: str
    preferred_callback_text: str | None = None
    source: CallbackSource


class CallbackAction(APIModel):
    id: UUID
    lead_id: UUID
    status: Literal["pending", "confirmed", "cancelled", "expired"]
    reason: str
    preferred_callback_text: str | None = None
    expires_at: datetime
