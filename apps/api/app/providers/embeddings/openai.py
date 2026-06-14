from __future__ import annotations

import os

from app.rag.exceptions import (
    DependencyUnavailableError,
    ProviderConfigurationError,
)


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        resolved_key = api_key or os.getenv("OPENAI_API_KEY")
        if not resolved_key:
            raise ProviderConfigurationError("OPENAI_API_KEY is required.")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise DependencyUnavailableError(
                "The 'openai' package is required for OpenAI embeddings."
            ) from exc

        self._client = AsyncOpenAI(api_key=resolved_key)
        self.model = model or os.getenv(
            "EMBEDDING_MODEL", "text-embedding-3-small"
        )
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        kwargs: dict[str, object] = {"model": self.model, "input": texts}
        if self.dimensions is not None:
            kwargs["dimensions"] = self.dimensions
        response = await self._client.embeddings.create(**kwargs)
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]
