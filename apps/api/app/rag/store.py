from __future__ import annotations

import asyncio
import os
import math
from collections import defaultdict

from app.providers.embeddings.base import EmbeddingProvider

from .models import DocumentChunk, RetrievalResult


def _cosine_similarity(left: tuple[float, ...], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    dot_product = sum(a * b for a, b in zip(left, right, strict=True))
    return dot_product / (left_norm * right_norm)


class InMemoryVectorStore:
    """Process-local retrieval store used when no external vector DB is configured."""

    def __init__(self, embedding_provider: EmbeddingProvider) -> None:
        self.embedding_provider = embedding_provider
        self._chunks: dict[str, list[DocumentChunk]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def add(self, chunks: list[DocumentChunk] | tuple[DocumentChunk, ...]) -> int:
        if not chunks:
            return 0
        embeddings = await self.embedding_provider.embed(
            [chunk.text for chunk in chunks]
        )
        if len(embeddings) != len(chunks):
            raise ValueError("Embedding provider returned an unexpected result count.")
        embedded = [
            chunk.with_embedding(embedding)
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        async with self._lock:
            for chunk in embedded:
                existing = self._chunks[chunk.document_id]
                existing[:] = [item for item in existing if item.id != chunk.id]
                existing.append(chunk)
        return len(embedded)

    async def delete_document(self, document_id: str) -> None:
        async with self._lock:
            self._chunks.pop(document_id, None)

    async def search(
        self,
        query: str,
        *,
        document_id: str,
        top_k: int = 5,
        min_score: float = 0.08,
    ) -> list[RetrievalResult]:
        if not query.strip() or top_k <= 0:
            return []
        query_embedding = (await self.embedding_provider.embed([query]))[0]
        async with self._lock:
            candidates = tuple(self._chunks.get(document_id, ()))
        results = [
            RetrievalResult(
                chunk=chunk,
                score=_cosine_similarity(chunk.embedding, query_embedding),
            )
            for chunk in candidates
        ]
        results.sort(key=lambda result: result.score, reverse=True)
        return [result for result in results[:top_k] if result.score >= min_score]

    async def count(self, document_id: str) -> int:
        async with self._lock:
            return len(self._chunks.get(document_id, ()))


class SupabaseVectorStore:
    """Persistent pgvector store accessed through Supabase REST/RPC."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        *,
        url: str,
        service_role_key: str,
    ) -> None:
        import httpx

        self.embedding_provider = embedding_provider
        self._client = httpx.AsyncClient(
            base_url=f"{url.rstrip('/')}/rest/v1/",
            headers={
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

    async def add(
        self, chunks: list[DocumentChunk] | tuple[DocumentChunk, ...]
    ) -> int:
        if not chunks:
            return 0
        embeddings = await self.embedding_provider.embed(
            [chunk.text for chunk in chunks]
        )
        rows = [
            {
                "id": chunk.id,
                "document_id": chunk.document_id,
                "page_number": chunk.page_number,
                "section_heading": chunk.section_heading,
                "chunk_index": chunk.chunk_index,
                "content": chunk.text,
                "embedding": embedding,
            }
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        response = await self._client.post(
            "document_chunks?on_conflict=document_id,page_number,chunk_index",
            headers={"Prefer": "resolution=merge-duplicates"},
            json=rows,
        )
        response.raise_for_status()
        return len(rows)

    async def delete_document(self, document_id: str) -> None:
        response = await self._client.delete(
            "document_chunks", params={"document_id": f"eq.{document_id}"}
        )
        response.raise_for_status()

    async def search(
        self,
        query: str,
        *,
        document_id: str,
        top_k: int = 5,
        min_score: float = 0.08,
    ) -> list[RetrievalResult]:
        if not query.strip():
            return []
        embedding = (await self.embedding_provider.embed([query]))[0]
        response = await self._client.post(
            "rpc/match_document_chunks",
            json={
                "query_embedding": embedding,
                "target_document_id": document_id,
                "match_count": top_k,
                "minimum_similarity": min_score,
            },
        )
        response.raise_for_status()
        return [
            RetrievalResult(
                chunk=DocumentChunk(
                    id=row["id"],
                    document_id=row["document_id"],
                    filename=row.get("filename", "Insurance product document"),
                    page_number=row["page_number"],
                    chunk_index=row["chunk_index"],
                    text=row["content"],
                    section_heading=row.get("section_heading"),
                    embedding=(),
                ),
                score=float(row["similarity"]),
            )
            for row in response.json()
        ]

    async def count(self, document_id: str) -> int:
        response = await self._client.get(
            "document_chunks",
            params={
                "select": "id",
                "document_id": f"eq.{document_id}",
            },
            headers={"Prefer": "count=exact"},
        )
        response.raise_for_status()
        content_range = response.headers.get("content-range", "*/0")
        return int(content_range.rsplit("/", 1)[-1])


def create_vector_store(embedding_provider: EmbeddingProvider):
    # RAG_VECTOR_STORE lets you decouple the embedding store from the relational
    # DB: "memory" forces the in-memory store even when Supabase is configured
    # for leads/callbacks (fast retrieval, no pgvector setup). "supabase" forces
    # pgvector. Unset = auto (Supabase if configured, else in-memory).
    backend = os.getenv("RAG_VECTOR_STORE", "").strip().lower()
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    use_supabase = backend == "supabase" or (
        backend != "memory" and bool(url and key)
    )
    if use_supabase and url and key:
        return SupabaseVectorStore(
            embedding_provider, url=url, service_role_key=key
        )
    return InMemoryVectorStore(embedding_provider)
