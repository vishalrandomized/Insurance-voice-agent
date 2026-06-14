from __future__ import annotations

from typing import Protocol

from app.rag.models import ConversationMessage


class LLMProvider(Protocol):
    async def generate(self, *, instructions: str, prompt: str) -> str:
        """Generate a complete response for later grounding verification."""

    async def summarize(self, messages: list[ConversationMessage]) -> str:
        """Create a concise conversation summary."""
