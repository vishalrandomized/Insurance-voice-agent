from __future__ import annotations

import os

from app.prompts.summary import SUMMARY_INSTRUCTIONS, build_summary_prompt
from app.rag.exceptions import (
    DependencyUnavailableError,
    ProviderConfigurationError,
)
from app.rag.models import ConversationMessage


class OpenAILLMProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        summary_model: str | None = None,
    ) -> None:
        resolved_key = api_key or os.getenv("OPENAI_API_KEY")
        if not resolved_key:
            raise ProviderConfigurationError("OPENAI_API_KEY is required.")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise DependencyUnavailableError(
                "The 'openai' package is required for the OpenAI LLM provider."
            ) from exc

        # Allow pointing at any OpenAI-compatible endpoint (e.g. Sarvam) via
        # OPENAI_BASE_URL. Such providers implement /chat/completions but NOT
        # OpenAI's newer Responses API, and some also want the key in an
        # api-subscription-key header in addition to the Bearer token.
        base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL")
        client_kwargs: dict[str, object] = {"api_key": resolved_key}
        self._use_responses = True
        # Extra params for the chat.completions path. Sarvam's models are
        # reasoning models: they emit a long chain-of-thought before the answer,
        # so the answer text (`content`) is only returned if max_tokens is large
        # enough to finish reasoning — otherwise content comes back null. Give a
        # generous budget and request the lowest reasoning effort. Tunable via
        # env; set LLM_REASONING_EFFORT empty for non-reasoning models.
        self._extra: dict[str, object] = {}
        if base_url:
            client_kwargs["base_url"] = base_url
            client_kwargs["default_headers"] = {
                "api-subscription-key": resolved_key
            }
            self._use_responses = False
            self._extra["max_tokens"] = int(os.getenv("LLM_MAX_TOKENS", "4000"))
            self._extra["temperature"] = float(
                os.getenv("LLM_TEMPERATURE", "0.2")
            )
            # reasoning_effort: "low"/"medium"/"high" to think first, or an
            # explicit JSON null to disable reasoning entirely (much faster).
            # Sent via extra_body because the OpenAI SDK drops None-valued
            # kwargs, but Sarvam needs the literal null to turn thinking off.
            effort = os.getenv("LLM_REASONING_EFFORT", "").strip().lower()
            if effort in ("low", "medium", "high"):
                self._extra["extra_body"] = {"reasoning_effort": effort}
            else:  # "", "none", "null", "off" -> no reasoning
                self._extra["extra_body"] = {"reasoning_effort": None}
        self._client = AsyncOpenAI(**client_kwargs)
        self.model = model or os.getenv("LLM_MODEL", "gpt-5-mini")
        self.summary_model = summary_model or os.getenv(
            "SUMMARY_MODEL", self.model
        )

    async def generate(self, *, instructions: str, prompt: str) -> str:
        if self._use_responses:
            response = await self._client.responses.create(
                model=self.model,
                instructions=instructions,
                input=prompt,
            )
            return response.output_text.strip()
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": prompt},
            ],
            **self._extra,
        )
        return (response.choices[0].message.content or "").strip()

    async def summarize(self, messages: list[ConversationMessage]) -> str:
        if not messages:
            return "No substantive conversation was recorded."
        prompt = build_summary_prompt(messages)
        if self._use_responses:
            response = await self._client.responses.create(
                model=self.summary_model,
                instructions=SUMMARY_INSTRUCTIONS,
                input=prompt,
            )
            return response.output_text.strip()
        response = await self._client.chat.completions.create(
            model=self.summary_model,
            messages=[
                {"role": "system", "content": SUMMARY_INSTRUCTIONS},
                {"role": "user", "content": prompt},
            ],
            **self._extra,
        )
        return (response.choices[0].message.content or "").strip()
