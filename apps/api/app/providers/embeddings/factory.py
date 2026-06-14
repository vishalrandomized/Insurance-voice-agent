from __future__ import annotations

import os

from .base import EmbeddingProvider
from .gemini import GeminiEmbeddingProvider
from .local import HashingEmbeddingProvider
from .openai import OpenAIEmbeddingProvider


def create_embedding_provider(
    provider: str | None = None,
    *,
    api_key: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
) -> EmbeddingProvider:
    selected = (provider or os.getenv("EMBEDDING_PROVIDER", "local")).lower()
    if selected in {"local", "hashing", "memory"}:
        local_dimensions = dimensions or int(
            os.getenv("LOCAL_EMBEDDING_DIMENSIONS", "384")
        )
        return HashingEmbeddingProvider(dimensions=local_dimensions)
    if selected == "openai":
        dimensions_value = os.getenv("EMBEDDING_DIMENSIONS")
        return OpenAIEmbeddingProvider(
            api_key=api_key,
            model=model,
            dimensions=dimensions
            or (int(dimensions_value) if dimensions_value else None),
        )
    if selected == "gemini":
        return GeminiEmbeddingProvider(api_key=api_key, model=model)
    raise ValueError(f"Unsupported embedding provider: {selected}")
