from __future__ import annotations

import os

import httpx

from app.rag.exceptions import ProviderConfigurationError


class GeminiEmbeddingProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
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
        self.model = model or os.getenv(
            "EMBEDDING_MODEL", "gemini-embedding-2"
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            content = text if text.startswith("task:") else f"task: search result | query: {text}"
            response = await self._client.post(
                f"models/{self.model}:embedContent",
                json={
                    "model": f"models/{self.model}",
                    "content": {"parts": [{"text": content}]},
                },
            )
            response.raise_for_status()
            payload = response.json()
            values = (
                payload.get("embedding", {}).get("values")
                or payload.get("embeddings", [{}])[0].get("values")
                or []
            )
            vectors.append([float(value) for value in values])
        return vectors

    async def close(self) -> None:
        await self._client.aclose()
