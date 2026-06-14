from __future__ import annotations

import asyncio
import math
import struct
from collections.abc import AsyncIterator

from .base import TTSProvider


class DemoTTSProvider(TTSProvider):
    """Produces short PCM tones so audio transport works without an API key."""

    content_type = "audio/pcm"

    def __init__(self, sample_rate: int = 24_000) -> None:
        self.sample_rate = sample_rate

    async def stream_audio(
        self, text: str, generation_id: int
    ) -> AsyncIterator[bytes]:
        duration = min(1.2, max(0.15, len(text) * 0.012))
        frame_count = int(self.sample_rate * duration)
        chunk_frames = 1_200
        for offset in range(0, frame_count, chunk_frames):
            frames = bytearray()
            for index in range(offset, min(offset + chunk_frames, frame_count)):
                envelope = max(0.0, 1.0 - (index / frame_count))
                sample = int(
                    1_200
                    * envelope
                    * math.sin(2 * math.pi * 440 * index / self.sample_rate)
                )
                frames.extend(struct.pack("<h", sample))
            await asyncio.sleep(0)
            yield bytes(frames)
