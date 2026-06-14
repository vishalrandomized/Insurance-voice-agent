from __future__ import annotations

from app.rag.models import ConversationMessage

SUMMARY_INSTRUCTIONS = """Summarize the insurance conversation for a salesperson.
Use only the supplied conversation. Do not add policy facts or infer sensitive
information. Include customer needs, products or benefits discussed, unresolved
questions, and callback preference when explicitly stated. Keep it under 120
words. If the conversation has no substantive content, return "No substantive
conversation was recorded."
"""


def build_summary_prompt(messages: list[ConversationMessage]) -> str:
    transcript = "\n".join(
        f"{message.role.upper()}: {message.text.strip()}" for message in messages
    )
    return f"<conversation>\n{transcript}\n</conversation>"
