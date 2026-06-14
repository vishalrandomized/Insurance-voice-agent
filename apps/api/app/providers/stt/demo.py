from __future__ import annotations

import asyncio
import base64
import os
from collections.abc import AsyncIterator
from uuid import uuid4

from .base import STTEvent, STTEventType, STTProvider


_CLOSE = object()


class DemoSTTProvider(STTProvider):
    """Local fallback.

    For UI development, base64 encode UTF-8 text prefixed with ``text:`` and
    send it through ``audio.append``. Real PCM produces a deterministic demo
    transcript on commit.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[STTEvent | object] = asyncio.Queue()
        self._buffer = bytearray()
        self._closed = False

    async def start(self) -> None:
        return None

    async def send_audio(self, audio_base64: str) -> None:
        try:
            decoded = base64.b64decode(audio_base64, validate=True)
        except Exception as exc:
            raise ValueError("audio must be valid base64") from exc
        self._buffer.extend(decoded)
        text = self._text_hint()
        if text:
            await self._queue.put(
                STTEvent(STTEventType.PARTIAL, text=text, item_id="demo-current")
            )

    async def commit(self) -> None:
        text = self._text_hint().strip()
        self._buffer.clear()
        if text:
            await self._queue.put(
                STTEvent(STTEventType.FINAL, text=text, item_id=f"demo-{uuid4()}")
            )
            return
        await self._queue.put(
            STTEvent(
                STTEventType.ERROR,
                text=(
                    "Live speech transcription is not configured. "
                    "Check the STT provider settings."
                ),
                error_code="demo_stt_no_live_provider",
                recoverable=True,
            )
        )

    async def events(self) -> AsyncIterator[STTEvent]:
        while True:
            event = await self._queue.get()
            if event is _CLOSE:
                return
            yield event  # type: ignore[misc]

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            await self._queue.put(_CLOSE)

    def _text_hint(self) -> str:
        try:
            value = self._buffer.decode("utf-8")
        except UnicodeDecodeError:
            return ""
        return value[5:].strip() if value.startswith("text:") else ""
