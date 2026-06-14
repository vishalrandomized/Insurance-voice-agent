from __future__ import annotations

import os

from .base import LLMProvider
from .gemini import GeminiLLMProvider
from .local import ExtractiveLLMProvider
from .openai import OpenAILLMProvider


def create_llm_provider(
    provider: str | None = None,
    *,
    api_key: str | None = None,
    model: str | None = None,
    summary_model: str | None = None,
) -> LLMProvider:
    selected = (provider or os.getenv("LLM_PROVIDER", "local")).lower()
    if selected in {"local", "extractive", "offline"}:
        return ExtractiveLLMProvider()
    if selected == "openai":
        return OpenAILLMProvider(
            api_key=api_key,
            model=model,
            summary_model=summary_model,
        )
    if selected == "gemini":
        return GeminiLLMProvider(
            api_key=api_key,
            model=model,
            summary_model=summary_model,
        )
    raise ValueError(f"Unsupported LLM provider: {selected}")
