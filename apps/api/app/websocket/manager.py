from __future__ import annotations

import asyncio


class DuplicateVoiceSessionError(RuntimeError):
    pass


class VoiceSessionRegistry:
    def __init__(self) -> None:
        self._active: set[str] = set()
        self._lock = asyncio.Lock()

    async def acquire(self, session_id: str) -> None:
        async with self._lock:
            if session_id in self._active:
                raise DuplicateVoiceSessionError(session_id)
            self._active.add(session_id)

    async def release(self, session_id: str) -> None:
        async with self._lock:
            self._active.discard(session_id)
