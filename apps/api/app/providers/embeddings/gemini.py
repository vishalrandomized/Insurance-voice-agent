from __future__ import annotations

import asyncio
import os

import httpx

from app.rag.exceptions import ProviderConfigurationError

# Gemini's embed endpoint intermittently returns 429/5xx under load. These are
# transient, so retry with backoff rather than failing the whole batch (which,
# at startup, would leave the agent ungrounded until the next restart).
_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 5


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

    async def _embed_one(self, content: str) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = await self._client.post(
                    f"models/{self.model}:embedContent",
                    json={
                        "model": f"models/{self.model}",
                        "content": {"parts": [{"text": content}]},
                    },
                )
                if response.status_code in _RETRY_STATUS:
                    raise httpx.HTTPStatusError(
                        f"transient {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return response
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                if attempt == _MAX_ATTEMPTS - 1:
                    break
                # 0.5, 1, 2, 4s backoff — rides out brief Gemini overloads.
                await asyncio.sleep(0.5 * (2 ** attempt))
        assert last_exc is not None
        raise last_exc

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            content = text if text.startswith("task:") else f"task: search result | query: {text}"
            response = await self._embed_one(content)
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
