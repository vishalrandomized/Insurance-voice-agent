from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from enum import Enum
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from .base import Repository, Row
from .errors import ConflictError, PersistenceError


class SupabaseRestRepository(Repository):
    """Small PostgREST client that keeps the API independent of a Supabase SDK."""

    def __init__(self, url: str, service_role_key: str, *, timeout: float = 10.0):
        self.base_url = f"{url.rstrip('/')}/rest/v1"
        self.key = service_role_key
        self.timeout = timeout

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
        session_payload = {
            "id": session_id,
            "product_id": product_id,
            "status": "active",
            "started_at": now,
        }
        session = (await self._request("POST", "sessions", body=session_payload))[0]
        try:
            lead_payload = {
                "id": lead_id,
                "session_id": session_id,
                "customer_name": customer_name,
                "phone": phone,
                "product_id": product_id,
                "callback_status": "not_requested",
                "created_at": now,
                "updated_at": now,
            }
            lead = (await self._request("POST", "leads", body=lead_payload))[0]
        except Exception:
            await self._request(
                "DELETE", "sessions", query={"id": f"eq.{session_id}"}
            )
            raise
        return session, lead

    async def end_session(
        self, session_id: UUID, *, status: str, ended_at: datetime
    ) -> Row:
        rows = await self._request(
            "PATCH",
            "sessions",
            query={"id": f"eq.{session_id}", "status": "eq.active"},
            body={"status": status, "ended_at": ended_at},
        )
        if rows:
            return rows[0]
        existing = await self.get_session(session_id)
        return existing or {}

    async def get_session(self, session_id: UUID) -> Row | None:
        return await self._one("sessions", {"id": f"eq.{session_id}"})

    async def get_lead(self, lead_id: UUID) -> Row | None:
        return await self._one("leads", {"id": f"eq.{lead_id}"})

    async def get_lead_by_session(self, session_id: UUID) -> Row | None:
        return await self._one("leads", {"session_id": f"eq.{session_id}"})

    async def list_leads(self, *, callback_status: str | None = None) -> list[Row]:
        query = {"order": "updated_at.desc"}
        if callback_status:
            query["callback_status"] = f"eq.{callback_status}"
        return await self._request("GET", "leads", query=query)

    async def update_lead(self, lead_id: UUID, values: Row) -> Row | None:
        rows = await self._request(
            "PATCH", "leads", query={"id": f"eq.{lead_id}"}, body=values
        )
        return rows[0] if rows else None

    async def create_callback_action(self, action: Row) -> Row:
        try:
            return (await self._request("POST", "callback_actions", body=action))[0]
        except PersistenceError as exc:
            if "duplicate" in str(exc).lower():
                raise ConflictError("Callback action already exists") from exc
            raise

    async def get_callback_action(self, action_id: UUID) -> Row | None:
        return await self._one(
            "callback_actions", {"id": f"eq.{action_id}"}
        )

    async def transition_callback_action(
        self, action_id: UUID, *, from_status: str, to_status: str
    ) -> Row | None:
        rows = await self._request(
            "PATCH",
            "callback_actions",
            query={"id": f"eq.{action_id}", "status": f"eq.{from_status}"},
            body={"status": to_status},
        )
        return rows[0] if rows else None

    async def create_audit_event(self, event: Row) -> Row:
        key = event.get("idempotency_key")
        try:
            return (await self._request("POST", "audit_events", body=event))[0]
        except PersistenceError:
            if key:
                existing = await self.get_audit_event_by_idempotency_key(key)
                if existing:
                    return existing
            raise

    async def get_audit_event_by_idempotency_key(self, key: str) -> Row | None:
        return await self._one(
            "audit_events", {"idempotency_key": f"eq.{key}"}
        )

    async def list_audit_events(self, lead_id: UUID) -> list[Row]:
        return await self._request(
            "GET",
            "audit_events",
            query={"lead_id": f"eq.{lead_id}", "order": "created_at.desc"},
        )

    async def healthcheck(self) -> bool:
        try:
            await self._request("GET", "leads", query={"select": "id", "limit": "1"})
            return True
        except PersistenceError:
            return False

    async def _one(self, table: str, query: dict[str, str]) -> Row | None:
        rows = await self._request(
            "GET", table, query={**query, "limit": "1"}
        )
        return rows[0] if rows else None

    async def _request(
        self,
        method: str,
        table: str,
        *,
        query: dict[str, str] | None = None,
        body: Row | None = None,
    ) -> list[Row]:
        return await asyncio.to_thread(
            self._request_sync, method, table, query or {}, body
        )

    def _request_sync(
        self, method: str, table: str, query: dict[str, str], body: Row | None
    ) -> list[Row]:
        url = f"{self.base_url}/{table}"
        if query:
            url = f"{url}?{urlencode(query)}"
        payload = (
            json.dumps(body, default=_json_default).encode("utf-8")
            if body is not None
            else None
        )
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
            headers["Prefer"] = "return=representation"
        request = Request(url, data=payload, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise PersistenceError(
                f"Supabase {method} {table} failed ({exc.code}): {detail}"
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise PersistenceError(
                f"Supabase {method} {table} failed: {exc}"
            ) from exc
        if not raw:
            return []
        result = json.loads(raw)
        return result if isinstance(result, list) else [result]


def _json_default(value: Any) -> str:
    if isinstance(value, (UUID, datetime, date, Enum)):
        return str(value.value if isinstance(value, Enum) else value)
    raise TypeError(f"Cannot serialize {type(value)!r}")
