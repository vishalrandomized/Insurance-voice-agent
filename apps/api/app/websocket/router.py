from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.providers.stt import create_stt_provider
from app.providers.tts import create_tts_provider
from app.voice import (
    ResponseStream,
    VoiceConfig,
    VoiceOrchestrator,
    demo_response_stream,
)

from .manager import DuplicateVoiceSessionError, VoiceSessionRegistry


router = APIRouter()
logger = logging.getLogger(__name__)
_registry = VoiceSessionRegistry()
_response_stream: ResponseStream = demo_response_stream
OPENING_PITCH_TRIGGER = "__OPENING_PITCH__"
END_CALLBACK_TRIGGER = "__END_CALLBACK__"

# After the cold-call opener, if the customer agrees to hear about the plan,
# deliver a brief grounded overview once per session (generated from the
# document, so it stays accurate — not a canned line). Tracked so a later "ok"
# acknowledgement doesn't re-trigger the pitch.
_overview_given: set[str] = set()
_OVERVIEW_QUERY = (
    "Give me a brief, friendly overview of this health plan — the main "
    "benefits and who it is a good fit for."
)
_AFFIRM_TOKENS = {
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "okey", "alright",
    "fine", "go", "ahead", "tell", "interested", "continue", "sounds",
    "please", "great", "definitely", "absolutely",
}
_NEGATE_TOKENS = {
    "no", "not", "nope", "nah", "dont", "stop", "busy", "later", "cant",
    "nevermind",
}


def _is_affirmation(text: str) -> bool:
    """True for a short 'go ahead / yes please' reply with no specific question
    and no negation — i.e. the customer agreeing to hear the pitch."""
    if "?" in text:
        return False
    words = re.findall(r"[a-z']+", text.lower())
    if not words or len(words) > 6:
        return False
    if any(w in _NEGATE_TOKENS for w in words):
        return False
    return any(w in _AFFIRM_TOKENS for w in words)


# Sessions where the agent has just SPOKEN the callback offer and is waiting for
# the customer's yes/no in the next transcript.
_awaiting_callback: set[str] = set()
_CALLBACK_YES = {
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "alright", "fine",
    "please", "definitely", "absolutely", "connect", "call", "interested",
    "sounds", "go", "ahead",
}


def _affirmative_reply(text: str) -> bool:
    """Lenient 'yes' to the spoken callback question (no word-count limit, but
    any negation word wins)."""
    words = set(re.findall(r"[a-z']+", text.lower()))
    if words & _NEGATE_TOKENS:
        return False
    return bool(words & _CALLBACK_YES)


def _negative_reply(text: str) -> bool:
    return bool(set(re.findall(r"[a-z']+", text.lower())) & _NEGATE_TOKENS)


async def _grounded_response_stream(
    transcript: str, context: Any
):
    from app.db import get_repository
    from app.models.schemas import CallbackActionCreate, CallbackSource
    from app.routes.documents import (
        active_policy_name,
        rag_service,
        resolve_active_document_id,
    )
    from app.services.callbacks import CallbackService
    from app.voice import ResponseDelta

    lowered = transcript.lower()
    if transcript == OPENING_PITCH_TRIGGER:
        # Hardcoded greeting — instant: no LLM, no retrieval, and crucially no
        # document resolution (which would re-ingest/embed the PDF on a cold
        # start). Only the cheap policy name is read here.
        answer = await rag_service.pitch(policy_name=active_policy_name())
        yield ResponseDelta(text=answer.text)
        return

    async def _record_callback(reason: str) -> bool:
        """Mark this session's lead callback as requested (create + confirm so
        it shows on the sales dashboard). True if a lead exists; an already-
        requested lead also counts as success."""
        repository = get_repository()
        lead = await repository.get_lead_by_session(UUID(context.session_id))
        if not lead:
            return False
        if str(lead.get("callback_status", "not_requested")) != "not_requested":
            return True
        service = CallbackService(repository)
        action = await service.create_action(
            lead["id"],
            CallbackActionCreate(
                reason=reason,
                preferred_callback_text=None,
                source=CallbackSource.CUSTOMER_VOICE,
            ),
        )
        await service.confirm_action(action.id)
        return True

    # The agent spoke the callback offer last turn — interpret this reply.
    if context.session_id in _awaiting_callback:
        _awaiting_callback.discard(context.session_id)
        if _affirmative_reply(transcript):
            try:
                await _record_callback(
                    "Customer agreed on the call to a human-advisor callback"
                )
            except Exception:
                pass
            yield ResponseDelta(
                text=(
                    "Wonderful — I've arranged for one of our advisors to call "
                    "you back and walk you through the next steps. Thank you for "
                    "your time today!"
                )
            )
            return
        if _negative_reply(transcript):
            yield ResponseDelta(
                text=(
                    "No problem at all. Thank you for taking the time today, and "
                    "feel free to reach out whenever you're ready."
                )
            )
            return
        # Ambiguous (e.g. a follow-up question) — drop the offer and answer it
        # normally below.

    # End-of-call: SPEAK the callback offer (no pop-up). The customer's reply on
    # the next turn (handled above) is what actually records the callback.
    if transcript == END_CALLBACK_TRIGGER:
        try:
            repository = get_repository()
            lead = await repository.get_lead_by_session(UUID(context.session_id))
            already = bool(lead) and str(
                lead.get("callback_status", "not_requested")
            ) != "not_requested"
        except Exception:
            already = False
        if already:
            yield ResponseDelta(
                text="We already have your callback request on file — thank you!"
            )
            return
        _awaiting_callback.add(context.session_id)
        yield ResponseDelta(
            text=(
                "Before you go — if you're interested, would you like to go "
                "ahead and have one of our human advisors call you to help you "
                "through the process?"
            )
        )
        return

    # Customer spontaneously asks for a callback at any point in the chat.
    if "callback" in lowered or "call me" in lowered:
        try:
            recorded = await _record_callback(
                "Customer asked for a callback while reviewing the policy"
            )
        except Exception:
            recorded = False
        if recorded:
            yield ResponseDelta(
                text=(
                    "Absolutely — I've arranged for one of our advisors to give "
                    "you a call. Is there anything else I can help you with?"
                )
            )
            return

    document_id = await resolve_active_document_id()
    if not document_id:
        yield ResponseDelta(
            text=(
                "I do not have an active insurance product document yet. "
                "Please upload the policy PDF from the sales dashboard first."
            )
        )
        return

    # Customer agreed to hear about the plan -> one-time grounded overview.
    if context.session_id not in _overview_given and _is_affirmation(transcript):
        _overview_given.add(context.session_id)
        query = _OVERVIEW_QUERY
    else:
        query = transcript

    answer = await rag_service.answer(query, document_id=document_id)
    citations = tuple(
        {
            "id": str(citation.id),
            "documentId": str(citation.document_id),
            "filename": citation.filename,
            "pageNumber": citation.page_number,
            "sectionHeading": citation.section_heading,
            "passage": citation.passage,
        }
        for citation in answer.citations
    )
    yield ResponseDelta(text=answer.text, citations=citations)


_response_stream = _grounded_response_stream


def configure_response_stream(handler: ResponseStream) -> None:
    """Wire the grounded RAG/LLM stream into newly created voice sessions."""

    global _response_stream
    _response_stream = handler


@router.websocket("/ws/voice/{session_id}")
async def voice_websocket(websocket: WebSocket, session_id: str) -> None:
    try:
        await _registry.acquire(session_id)
    except DuplicateVoiceSessionError:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="voice_session_already_connected",
        )
        return

    await websocket.accept()
    config = VoiceConfig.from_env()
    orchestrator: VoiceOrchestrator | None = None
    started = False

    async def send_event(event: dict[str, Any]) -> None:
        await websocket.send_json(event)

    try:
        stt = create_stt_provider(config)
        tts = create_tts_provider(config)
        orchestrator = VoiceOrchestrator(
            session_id=session_id,
            stt=stt,
            tts=tts,
            response_stream=_response_stream,
            send_event=send_event,
            config=config,
        )

        while True:
            raw = await websocket.receive_text()
            try:
                event = json.loads(raw)
                _validate_client_event(event, session_id)
                event_type = event["type"]
                print(
                    f"[voice] session_id={session_id} event_type={event_type}",
                    flush=True,
                )

                if event_type == "session.start":
                    if not started:
                        logger.info("voice session.start session_id=%s", session_id)
                        await orchestrator.start()
                        started = True
                elif not started:
                    await _send_error(
                        websocket,
                        session_id,
                        orchestrator.generation_id,
                        "session_not_started",
                        "Send session.start before audio events.",
                        True,
                    )
                elif event_type == "audio.append":
                    logger.info(
                        "voice audio.append session_id=%s bytes_b64=%s",
                        session_id,
                        len(event["audio"]),
                    )
                    await orchestrator.append_audio(event["audio"])
                elif event_type == "audio.commit":
                    logger.info("voice audio.commit session_id=%s", session_id)
                    await orchestrator.commit_audio()
                elif event_type == "text.submit":
                    logger.info("voice text.submit session_id=%s", session_id)
                    await orchestrator.submit_text(event["text"])
                elif event_type == "response.cancel":
                    logger.info("voice response.cancel session_id=%s", session_id)
                    await orchestrator.cancel_response(event["generationId"])
                elif event_type == "session.end":
                    return
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                generation = orchestrator.generation_id if orchestrator else 0
                await _send_error(
                    websocket,
                    session_id,
                    generation,
                    "invalid_voice_event",
                    str(exc),
                    True,
                )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        generation = orchestrator.generation_id if orchestrator else 0
        try:
            await _send_error(
                websocket,
                session_id,
                generation,
                "voice_session_failed",
                str(exc),
                False,
            )
        except Exception:
            pass
    finally:
        if orchestrator:
            await orchestrator.close()
        await _registry.release(session_id)


def _validate_client_event(event: Any, path_session_id: str) -> None:
    if not isinstance(event, dict):
        raise TypeError("WebSocket event must be a JSON object")
    event_type = event.get("type")
    allowed = {
        "session.start",
        "audio.append",
        "audio.commit",
        "response.cancel",
        "session.end",
        "text.submit",
    }
    if event_type not in allowed:
        raise ValueError(f"Unsupported event type: {event_type}")
    if event.get("sessionId") != path_session_id:
        raise ValueError("Event sessionId does not match WebSocket path")
    if event_type == "audio.append" and not isinstance(event.get("audio"), str):
        raise TypeError("audio.append requires a base64 audio string")
    if event_type == "response.cancel" and not isinstance(
        event.get("generationId"), int
    ):
        raise TypeError("response.cancel requires an integer generationId")
    if event_type == "text.submit" and not isinstance(event.get("text"), str):
        raise TypeError("text.submit requires a text string")


async def _send_error(
    websocket: WebSocket,
    session_id: str,
    generation_id: int,
    code: str,
    message: str,
    recoverable: bool,
) -> None:
    await websocket.send_json(
        {
            "type": "session.error",
            "sessionId": session_id,
            "generationId": generation_id,
            "code": code,
            "message": message,
            "recoverable": recoverable,
        }
    )
