import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import reset_repository
from app.db.errors import ConflictError
from app.db.memory import InMemoryRepository
from app.main import app
from app.models.schemas import (
    CallbackActionCreate,
    CallbackSource,
    CallbackStatus,
    CallbackUpdate,
    SessionCreate,
)
from app.services.callbacks import CallbackService
from app.services.leads import LeadService
from app.services.sessions import SessionService


def run(coro):
    return asyncio.run(coro)


def test_session_creation_and_abandonment():
    repository = InMemoryRepository()
    sessions = SessionService(repository)

    created = run(
        sessions.create_session(
            SessionCreate(customer_name="  Asha  ", phone=" 9999999999 ")
        )
    )
    ended = run(sessions.end_session(created.session_id, abandoned=True))

    assert created.lead.customer_name == "Asha"
    assert created.lead.phone == "9999999999"
    assert ended["status"] == "abandoned"
    assert ended["ended_at"] is not None


def test_callback_confirmation_is_idempotent_and_audited_once():
    repository = InMemoryRepository()
    sessions = SessionService(repository)
    callbacks = CallbackService(repository)
    leads = LeadService(repository)
    created = run(sessions.create_session(SessionCreate(product_id=uuid4())))

    action = run(
        callbacks.create_action(
            created.lead.id,
            CallbackActionCreate(
                reason="Needs family plan guidance",
                preferred_callback_text="Tomorrow afternoon",
                source=CallbackSource.CUSTOMER_VOICE,
            ),
        )
    )
    first = run(callbacks.confirm_action(action.id))
    second = run(callbacks.confirm_action(action.id))
    audit = run(leads.list_audit_events(created.lead.id))

    assert first.callback_status == CallbackStatus.REQUESTED
    assert second == first
    assert len(audit) == 1
    assert audit[0].event_type == "callback_requested"
    assert audit[0].source == CallbackSource.CUSTOMER_VOICE


def test_cancelled_callback_action_cannot_be_confirmed():
    repository = InMemoryRepository()
    sessions = SessionService(repository)
    callbacks = CallbackService(repository)
    created = run(sessions.create_session(SessionCreate(product_id=uuid4())))
    action = run(
        callbacks.create_action(
            created.lead.id,
            CallbackActionCreate(
                reason="Asked for a callback",
                source=CallbackSource.CUSTOMER_UI,
            ),
        )
    )

    cancelled = run(callbacks.cancel_action(action.id))
    assert cancelled.status == "cancelled"

    try:
        run(callbacks.confirm_action(action.id))
    except ConflictError as exc:
        assert "cancelled" in str(exc)
    else:
        raise AssertionError("Cancelled action should not be confirmable")


def test_salesperson_status_update_persists_audit_event():
    repository = InMemoryRepository()
    sessions = SessionService(repository)
    leads = LeadService(repository)
    created = run(sessions.create_session(SessionCreate(product_id=uuid4())))

    requested = run(
        leads.update_callback(
            created.lead.id,
            CallbackUpdate(
                status=CallbackStatus.REQUESTED,
                reason="Customer requested contact",
                source=CallbackSource.CUSTOMER_UI,
            ),
        )
    )
    completed = run(
        leads.update_callback(
            created.lead.id,
            CallbackUpdate(
                status=CallbackStatus.COMPLETED,
                reason=requested.callback_reason,
                source=CallbackSource.SALESPERSON,
            ),
        )
    )
    audit = run(leads.list_audit_events(created.lead.id))

    assert completed.callback_status == CallbackStatus.COMPLETED
    assert len(audit) == 2
    assert audit[0].payload["previous_status"] == "requested"


def test_http_callback_flow_updates_sales_dashboard_state():
    repository = InMemoryRepository()
    reset_repository(repository)
    client = TestClient(app)
    product_id = str(uuid4())

    session_response = client.post(
        "/api/sessions",
        json={
            "product_id": product_id,
            "customer_name": "Ravi",
            "phone": "9876543210",
        },
    )
    assert session_response.status_code == 201
    lead_id = session_response.json()["lead"]["id"]

    action_response = client.post(
        f"/api/leads/{lead_id}/callback-actions",
        json={
            "reason": "Wants help understanding exclusions",
            "preferred_callback_text": "Friday morning",
            "source": "customer_voice",
        },
    )
    assert action_response.status_code == 201
    action_id = action_response.json()["id"]

    first_confirmation = client.post(
        f"/api/callback-actions/{action_id}/confirm"
    )
    repeated_confirmation = client.post(
        f"/api/callback-actions/{action_id}/confirm"
    )
    assert first_confirmation.status_code == 200
    assert repeated_confirmation.status_code == 200
    assert first_confirmation.json()["callback_status"] == "requested"
    assert repeated_confirmation.json() == first_confirmation.json()

    leads_response = client.get(
        "/api/leads", params={"callback_status": "requested"}
    )
    audit_response = client.get(f"/api/leads/{lead_id}/audit-events")
    assert leads_response.status_code == 200
    assert [lead["id"] for lead in leads_response.json()] == [lead_id]
    assert audit_response.status_code == 200
    assert len(audit_response.json()) == 1
    assert audit_response.json()[0]["event_type"] == "callback_requested"
