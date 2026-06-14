from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlencode

from .base import STTEvent, STTEventType, STTProvider


_CLOSE = object()
logger = logging.getLogger(__name__)


class AssemblyAIStreamingSTTProvider(STTProvider):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str,
        sample_rate: int,
    ) -> None:
        resolved_key = api_key or os.getenv("ASSEMBLYAI_API_KEY")
        if not resolved_key:
            raise ValueError("ASSEMBLYAI_API_KEY is required for AssemblyAI STT")
        self._api_key = resolved_key
        self._model = model or "u3-rt-pro"
        self._sample_rate = sample_rate
        self._socket: Any = None
        self._receiver: asyncio.Task[None] | None = None
        self._queue: asyncio.Queue[STTEvent | object] = asyncio.Queue()

    async def start(self) -> None:
        try:
            from websockets.asyncio.client import connect
        except ImportError as exc:
            raise RuntimeError(
                "Install websockets support to use STT_PROVIDER=assemblyai"
            ) from exc

        params = urlencode(
            {"sample_rate": self._sample_rate, "speech_model": self._model}
        )
        self._socket = await connect(
            f"wss://streaming.assemblyai.com/v3/ws?{params}",
            additional_headers={"Authorization": self._api_key},
            max_size=4 * 1024 * 1024,
        )
        print(
            f"[assemblyai] connected model={self._model} sample_rate={self._sample_rate}",
            flush=True,
        )
        logger.info(
            "AssemblyAI STT connected: model=%s sample_rate=%s",
            self._model,
            self._sample_rate,
        )
        self._receiver = asyncio.create_task(
            self._receive_events(), name="assemblyai-stt-receiver"
        )

    async def send_audio(self, audio_base64: str) -> None:
        if self._socket is None:
            raise RuntimeError("STT provider has not been started")
        payload = base64.b64decode(audio_base64)
        if len(payload) > 0:
            print(f"[assemblyai] send_audio bytes={len(payload)}", flush=True)
        logger.debug("AssemblyAI STT send_audio bytes=%s", len(payload))
        await self._socket.send(payload)

    async def commit(self) -> None:
        if self._socket is None:
            return
        try:
            await self._socket.send(json.dumps({"type": "ForceEndpoint"}))
            print("[assemblyai] sent ForceEndpoint", flush=True)
        except Exception as exc:
            print(f"[assemblyai] ForceEndpoint failed: {exc}", flush=True)

    async def events(self) -> AsyncIterator[STTEvent]:
        while True:
            event = await self._queue.get()
            if event is _CLOSE:
                return
            yield event  # type: ignore[misc]

    async def close(self) -> None:
        if self._receiver:
            self._receiver.cancel()
            await asyncio.gather(self._receiver, return_exceptions=True)
        if self._socket:
            try:
                await self._socket.send(json.dumps({"type": "Terminate"}))
            except Exception:
                pass
            await self._socket.close()
        await self._queue.put(_CLOSE)

    async def _receive_events(self) -> None:
        try:
            async for raw in self._socket:
                payload = json.loads(raw)
                event_type = payload.get("type")
                print(f"[assemblyai] recv type={event_type} payload={payload}", flush=True)
                logger.info("AssemblyAI STT event type=%s", event_type)
                if payload.get("type") == "Turn":
                    transcript = (payload.get("transcript") or "").strip()
                    if not transcript:
                        continue
                    await self._queue.put(
                        STTEvent(
                            STTEventType.FINAL
                            if payload.get("end_of_turn")
                            else STTEventType.PARTIAL,
                            text=transcript,
                            item_id=str(payload.get("turn_order", "")),
                        )
                    )
                elif payload.get("error"):
                    logger.error("AssemblyAI STT error payload=%s", payload)
                    await self._queue.put(
                        STTEvent(
                            STTEventType.ERROR,
                            text=str(payload.get("error")),
                            error_code="assemblyai_error",
                            recoverable=True,
                        )
                    )
                else:
                    logger.info("AssemblyAI STT unhandled payload=%s", payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("AssemblyAI STT receiver failed")
            await self._queue.put(
                STTEvent(
                    STTEventType.ERROR,
                    text=str(exc),
                    error_code="assemblyai_connection_lost",
                    recoverable=True,
                )
            )
