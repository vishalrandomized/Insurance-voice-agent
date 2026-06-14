from __future__ import annotations

import contextlib
import json
import os
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlencode

from .base import TTSProvider


class DeepgramTTSProvider(TTSProvider):
    content_type = "audio/pcm"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str,
        sample_rate: int = 24_000,
    ) -> None:
        resolved_key = api_key or os.getenv("DEEPGRAM_API_KEY")
        if not resolved_key:
            raise ValueError("DEEPGRAM_API_KEY is required for Deepgram TTS")
        self._api_key = resolved_key
        self._model = model or "aura-2-thalia-en"
        self.sample_rate = sample_rate

    async def stream_audio(
        self, text: str, generation_id: int
    ) -> AsyncIterator[bytes]:
        del generation_id
        try:
            from websockets.asyncio.client import connect
        except ImportError as exc:
            raise RuntimeError(
                "Install websockets support to use TTS_PROVIDER=deepgram"
            ) from exc

        params = urlencode(
            {
                "model": self._model,
                "encoding": "linear16",
                "sample_rate": self.sample_rate,
            }
        )
        socket: Any = await connect(
            f"wss://api.deepgram.com/v1/speak?{params}",
            additional_headers={"Authorization": f"Token {self._api_key}"},
            max_size=8 * 1024 * 1024,
        )
        try:
            await socket.send(json.dumps({"type": "Speak", "text": text}))
            await socket.send(json.dumps({"type": "Flush"}))
            while True:
                message = await socket.recv()
                if isinstance(message, bytes):
                    yield message
                    continue
                payload = json.loads(message)
                event_type = str(payload.get("type", "")).lower()
                if event_type in {"flushed", "close", "closed"}:
                    break
                if event_type == "error":
                    raise RuntimeError(
                        payload.get("description", "Deepgram TTS failed")
                    )
        finally:
            with contextlib.suppress(Exception):
                await socket.send(json.dumps({"type": "Close"}))
            await socket.close()
