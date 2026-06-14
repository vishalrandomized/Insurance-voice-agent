from __future__ import annotations

import logging

from app.rag.models import ConversationMessage

from .base import LLMProvider
from .local import ExtractiveLLMProvider

logger = logging.getLogger(__name__)


class FallbackLLMProvider:
    """Wraps a remote LLM provider and degrades to an offline extractive
    provider when the remote call fails.

    The Gemini free tier returns 429 (rate/quota) and occasionally 503; without
    this wrapper those propagate as a session.error and the agent goes silent.
    Falling back to the extractive provider keeps the agent answering verbatim
    from the document (never hallucinated) instead of failing the turn.
    """

    def __init__(
        self, primary: LLMProvider, fallback: LLMProvider | None = None
    ) -> None:
        self._primary = primary
        self._fallback = fallback or ExtractiveLLMProvider()

    async def generate(self, *, instructions: str, prompt: str) -> str:
        try:
            return await self._primary.generate(
                instructions=instructions, prompt=prompt
            )
        except Exception as exc:  # noqa: BLE001 - any remote failure degrades
            print(
                f"[llm] primary generate failed ({exc!r}); using extractive fallback",
                flush=True,
            )
            logger.warning("LLM generate fell back to extractive: %s", exc)
            return await self._fallback.generate(
                instructions=instructions, prompt=prompt
            )

    async def summarize(self, messages: list[ConversationMessage]) -> str:
        try:
            return await self._primary.summarize(messages)
        except Exception as exc:  # noqa: BLE001
            print(
                f"[llm] primary summarize failed ({exc!r}); using extractive fallback",
                flush=True,
            )
            logger.warning("LLM summarize fell back to extractive: %s", exc)
            return await self._fallback.summarize(messages)

    async def close(self) -> None:
        close = getattr(self._primary, "close", None)
        if close is not None:
            await close()
