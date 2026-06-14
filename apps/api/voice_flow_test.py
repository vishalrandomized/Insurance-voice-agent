"""Drives the exact WebSocket voice-flow protocol the browser client uses.

Replicates /customer: upload PDF -> create session -> session.start ->
opening pitch -> grounded question -> end-of-call callback -> confirm.
Uses the text.submit path (same server pipeline as voice, minus the mic).
"""
from __future__ import annotations

import asyncio
import json
import os

import httpx
import websockets

API = "http://127.0.0.1:8000"
WS = "ws://127.0.0.1:8000"
PDF = os.path.join(os.path.dirname(__file__), "..", "..", "Setu_Sampoorna_Prospectus.md.pdf")


def show(events, label):
    text = "".join(e.get("delta", "") for e in events if e.get("type") == "agent.text.delta")
    complete = next((e for e in events if e.get("type") == "agent.text.complete"), None)
    if complete and complete.get("text"):
        text = complete["text"]
    citations = [e["citation"] for e in events if e.get("type") == "citation.created"]
    errors = [e for e in events if e.get("type") == "session.error"]
    proposals = [e for e in events if e.get("type") == "callback.proposed"]
    print(f"\n===== {label} =====")
    print("event types:", [e["type"] for e in events])
    if text:
        print("\nAGENT TEXT:\n" + text.strip())
    for c in citations:
        passage = " ".join(str(c.get("passage", "")).split())
        if len(passage) > 160:
            passage = passage[:157] + "..."
        print(f"  CITATION p{c.get('pageNumber')} [{c.get('sectionHeading') or c.get('filename')}]: {passage}")
    for p in proposals:
        print(f"  CALLBACK PROPOSED actionId={p.get('actionId')} reason={p.get('reason')!r}")
    for err in errors:
        print(f"  ERROR code={err.get('code')} msg={err.get('message')}")
    return citations, proposals


async def recv_until(ws, stop_types, timeout=90):
    events = []
    while True:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        except asyncio.TimeoutError:
            events.append({"type": "__timeout__"})
            return events
        ev = json.loads(raw)
        events.append(ev)
        if ev.get("type") in stop_types:
            return events


async def main():
    async with httpx.AsyncClient(timeout=180) as client:
        with open(os.path.abspath(PDF), "rb") as f:
            r = await client.post(
                f"{API}/api/documents",
                files={"file": ("Setu_Sampoorna_Prospectus.pdf", f, "application/pdf")},
            )
        print("UPLOAD", r.status_code)
        print(json.dumps(r.json(), indent=2) if r.status_code < 300 else r.text)
        if r.status_code >= 300:
            return

        r = await client.post(
            f"{API}/api/sessions", json={"customer_name": "Demo Customer", "phone": None}
        )
        print("SESSION", r.status_code, r.text)
        data = r.json()
        session_id = data.get("session_id") or data.get("sessionId") or data.get("id")

    uri = f"{WS}/ws/voice/{session_id}"
    action_id = None
    async with websockets.connect(uri, max_size=8 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"type": "session.start", "sessionId": session_id}))
        evs = await recv_until(ws, {"session.ready"}, 30)
        print("\n===== SESSION.READY =====")
        print("event types:", [e["type"] for e in evs])

        await ws.send(json.dumps({"type": "text.submit", "sessionId": session_id, "text": "__OPENING_PITCH__"}))
        show(await recv_until(ws, {"agent.text.complete", "session.error"}), "OPENING PITCH")

        await ws.send(json.dumps({"type": "text.submit", "sessionId": session_id, "text": "What are the main benefits of this policy?"}))
        show(await recv_until(ws, {"agent.text.complete", "session.error"}), "QUESTION: main benefits")

        await ws.send(json.dumps({"type": "text.submit", "sessionId": session_id, "text": "Are there any waiting periods or exclusions?"}))
        show(await recv_until(ws, {"agent.text.complete", "session.error"}), "QUESTION: waiting periods")

        await ws.send(json.dumps({"type": "text.submit", "sessionId": session_id, "text": "__END_CALLBACK__"}))
        _, proposals = show(await recv_until(ws, {"callback.proposed", "agent.text.complete", "session.error"}, 60), "END-OF-CALL CALLBACK OFFER")
        if proposals:
            action_id = proposals[0].get("actionId")

    print("\n===== CONFIRM CALLBACK (customer accepts) =====")
    if action_id:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{API}/api/callback-actions/{action_id}/confirm")
            print("CONFIRM", r.status_code, r.text[:400])
            r = await client.get(f"{API}/api/leads")
            print("\nSALES DASHBOARD /api/leads:", r.status_code)
            print(json.dumps(r.json(), indent=2)[:800])
    else:
        print("no callback proposed (skipping)")


if __name__ == "__main__":
    asyncio.run(main())
