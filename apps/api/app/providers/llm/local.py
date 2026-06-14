from __future__ import annotations

import re

from app.rag.models import ConversationMessage

EVIDENCE_RE = re.compile(
    r'<evidence id="(?P<id>C\d+)"[^>]*>\s*(?P<text>.*?)\s*</evidence>',
    re.DOTALL,
)


class ExtractiveLLMProvider:
    """Offline fallback that returns evidence verbatim instead of hallucinating."""

    async def generate(self, *, instructions: str, prompt: str) -> str:
        del instructions
        evidence = EVIDENCE_RE.search(prompt)
        if not evidence:
            return ""
        text = " ".join(evidence.group("text").split())
        # Keep spoken answers concise (this is the offline fallback used when the
        # LLM is rate-limited); a shorter excerpt is far better for a voice turn.
        if len(text) > 240:
            text = text[:237].rsplit(" ", 1)[0] + "..."
        return f"According to the product document: {text} [{evidence.group('id')}]"

    async def summarize(self, messages: list[ConversationMessage]) -> str:
        if not messages:
            return "No substantive conversation was recorded."
        substantive = [
            f"{message.role.title()}: {' '.join(message.text.split())}"
            for message in messages
            if message.text.strip()
        ]
        if not substantive:
            return "No substantive conversation was recorded."
        summary = " ".join(substantive)
        return summary if len(summary) <= 700 else summary[:697].rsplit(" ", 1)[0] + "..."
