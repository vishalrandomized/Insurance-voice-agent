from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from .base import TTSProvider


class OpenAITTSProvider(TTSProvider):
    content_type = "audio/pcm"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        voice: str,
        sample_rate: int = 24_000,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI TTS")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "Install the openai Python package to use TTS_PROVIDER=openai"
            ) from exc
        self.sample_rate = sample_rate
        self._client: Any = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._voice = voice

    async def stream_audio(
        self, text: str, generation_id: int
    ) -> AsyncIterator[bytes]:
        async with self._client.audio.speech.with_streaming_response.create(
            model=self._model,
            voice=self._voice,
            input=text,
            response_format="pcm",
            instructions=(
                "Speak clearly, calmly, and professionally as an insurance "
                "product assistant. Do not add words that are not in the input."
            ),
        ) as response:
            async for chunk in response.iter_bytes(chunk_size=16_384):
                yield chunk

    async def close(self) -> None:
        await self._client.close()
