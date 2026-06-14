from __future__ import annotations

import re


_BOUNDARY = re.compile(r"(?<=[.!?])(?:[\"')\]]*)\s+")
_ABBREVIATIONS = {
    "dr.",
    "e.g.",
    "i.e.",
    "mr.",
    "mrs.",
    "ms.",
    "no.",
    "prof.",
    "sr.",
    "vs.",
}


class SentenceBuffer:
    """Incrementally extracts conservative TTS-sized text segments."""

    def __init__(self, max_chars: int = 180) -> None:
        self._buffer = ""
        self._max_chars = max_chars

    def push(self, delta: str) -> list[str]:
        self._buffer += delta
        return self._drain(complete=False)

    def flush(self) -> list[str]:
        return self._drain(complete=True)

    def _drain(self, *, complete: bool) -> list[str]:
        segments: list[str] = []
        while self._buffer:
            boundary = self._sentence_boundary()
            if boundary is None and len(self._buffer) >= self._max_chars:
                boundary = self._soft_boundary()
            if boundary is None:
                if complete and self._buffer.strip():
                    segments.append(self._buffer.strip())
                    self._buffer = ""
                break

            candidate = self._buffer[:boundary].strip()
            self._buffer = self._buffer[boundary:].lstrip()
            if candidate:
                segments.append(candidate)
        return segments

    def _sentence_boundary(self) -> int | None:
        for match in _BOUNDARY.finditer(self._buffer):
            candidate = self._buffer[: match.start() + 1].rstrip("\"')]} ")
            last_token = candidate.rsplit(maxsplit=1)[-1].lower()
            if last_token not in _ABBREVIATIONS:
                return match.end()
        return None

    def _soft_boundary(self) -> int:
        window = self._buffer[: self._max_chars + 1]
        for separator in (", ", "; ", ": ", " "):
            index = window.rfind(separator)
            if index >= self._max_chars // 2:
                return index + len(separator)
        return min(len(self._buffer), self._max_chars)
