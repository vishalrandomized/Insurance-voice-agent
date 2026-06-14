from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from .base import STTEvent, STTEventType, STTProvider


_CLOSE = object()


class OpenAIRealtimeSTTProvider(STTProvider):
    """OpenAI transcription-only Realtime WebSocket adapter."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        language: str,
        delay: str,
        sample_rate: int,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI STT")
        self._api_key = api_key
        self._model = model
        self._language = language
        self._delay = delay
        self._sample_rate = sample_rate
        self._socket: Any = None
        self._receiver: asyncio.Task[None] | None = None
        self._queue: asyncio.Queue[STTEvent | object] = asyncio.Queue()

    async def start(self) -> None:
        try:
            from websockets.asyncio.client import connect
        except ImportError as exc:
            raise RuntimeError(
                "Install websockets>=13 to use STT_PROVIDER=openai"
            ) from exc

        url = f"wss://api.openai.com/v1/realtime?model={self._model}"
        self._socket = await connect(
            url,
            additional_headers={"Authorization": f"Bearer {self._api_key}"},
            max_size=4 * 1024 * 1024,
        )
        await self._send(
            {
                "type": "session.update",
                "session": {
                    "type": "transcription",
                    "audio": {
                        "input": {
                            "format": {
                                "type": "audio/pcm",
                                "rate": self._sample_rate,
                            },
                            "transcription": {
                                "model": self._model,
                                "language": self._language,
                                "delay": self._delay,
                            },
                            # gpt-realtime-whisper currently uses manual commits.
                            "turn_detection": None,
                        }
                    },
                },
            }
        )
        self._receiver = asyncio.create_task(
            self._receive_events(), name="openai-stt-receiver"
        )

    async def send_audio(self, audio_base64: str) -> None:
        await self._send(
            {"type": "input_audio_buffer.append", "audio": audio_base64}
        )

    async def commit(self) -> None:
        await self._send({"type": "input_audio_buffer.commit"})

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
            await self._socket.close()
        await self._queue.put(_CLOSE)

    async def _send(self, event: dict[str, Any]) -> None:
        if self._socket is None:
            raise RuntimeError("STT provider has not been started")
        await self._socket.send(json.dumps(event))

    async def _receive_events(self) -> None:
        try:
            async for raw in self._socket:
                event = json.loads(raw)
                event_type = event.get("type")
                item_id = event.get("item_id")
                if event_type == (
                    "conversation.item.input_audio_transcription.delta"
                ):
                    await self._queue.put(
                        STTEvent(
                            STTEventType.PARTIAL,
                            text=event.get("delta", ""),
                            item_id=item_id,
                        )
                    )
                elif event_type == (
                    "conversation.item.input_audio_transcription.completed"
                ):
                    await self._queue.put(
                        STTEvent(
                            STTEventType.FINAL,
                            text=event.get("transcript", ""),
                            item_id=item_id,
                        )
                    )
                elif event_type == "error":
                    error = event.get("error", {})
                    await self._queue.put(
                        STTEvent(
                            STTEventType.ERROR,
                            text=error.get("message", "Transcription failed"),
                            error_code=error.get("code", "stt_provider_error"),
                            recoverable=True,
                        )
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._queue.put(
                STTEvent(
                    STTEventType.ERROR,
                    text=str(exc),
                    error_code="stt_connection_lost",
                    recoverable=True,
                )
            )
