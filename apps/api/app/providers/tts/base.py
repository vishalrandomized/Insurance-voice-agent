from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class TTSProvider(ABC):
    content_type: str = "audio/pcm"
    sample_rate: int = 24_000

    @abstractmethod
    def stream_audio(
        self, text: str, generation_id: int
    ) -> AsyncIterator[bytes]:
        raise NotImplementedError

    async def close(self) -> None:
        return None
