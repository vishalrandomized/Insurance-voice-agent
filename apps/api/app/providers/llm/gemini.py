from __future__ import annotations

import os
from typing import Any

import httpx

from app.prompts.summary import SUMMARY_INSTRUCTIONS, build_summary_prompt
from app.rag.exceptions import ProviderConfigurationError
from app.rag.models import ConversationMessage


class GeminiLLMProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        summary_model: str | None = None,
    ) -> None:
        resolved_key = api_key or os.getenv("GEMINI_API_KEY")
        if not resolved_key:
            raise ProviderConfigurationError("GEMINI_API_KEY is required.")
        self._client = httpx.AsyncClient(
            base_url="https://generativelanguage.googleapis.com/v1beta/",
            headers={
                "x-goog-api-key": resolved_key,
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        self.model = model or os.getenv("LLM_MODEL", "gemini-2.0-flash")
        self.summary_model = summary_model or os.getenv(
            "SUMMARY_MODEL", self.model
        )

    async def generate(self, *, instructions: str, prompt: str) -> str:
        response = await self._client.post(
            f"models/{self.model}:generateContent",
            json={
                "system_instruction": {"parts": [{"text": instructions}]},
                "contents": [{"parts": [{"text": prompt}]}],
            },
        )
        response.raise_for_status()
        return _extract_text(response.json()).strip()

    async def summarize(self, messages: list[ConversationMessage]) -> str:
        if not messages:
            return "No substantive conversation was recorded."
        response = await self._client.post(
            f"models/{self.summary_model}:generateContent",
            json={
                "system_instruction": {
                    "parts": [{"text": SUMMARY_INSTRUCTIONS}]
                },
                "contents": [
                    {"parts": [{"text": build_summary_prompt(messages)}]}
                ],
            },
        )
        response.raise_for_status()
        return _extract_text(response.json()).strip()

    async def close(self) -> None:
        await self._client.aclose()


def _extract_text(payload: dict[str, Any]) -> str:
    texts: list[str] = []
    for candidate in payload.get("candidates") or []:
        content = candidate.get("content") or {}
        for part in content.get("parts") or []:
            text = part.get("text")
            if text:
                texts.append(text)
    return "".join(texts)
