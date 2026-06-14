from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence


@dataclass(frozen=True, slots=True)
class DocumentPage:
    document_id: str
    filename: str
    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    id: str
    document_id: str
    filename: str
    page_number: int
    chunk_index: int
    text: str
    section_heading: str | None = None
    embedding: tuple[float, ...] = ()

    def with_embedding(self, embedding: Sequence[float]) -> DocumentChunk:
        return DocumentChunk(
            id=self.id,
            document_id=self.document_id,
            filename=self.filename,
            page_number=self.page_number,
            chunk_index=self.chunk_index,
            text=self.text,
            section_heading=self.section_heading,
            embedding=tuple(float(value) for value in embedding),
        )


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    chunk: DocumentChunk
    score: float


@dataclass(frozen=True, slots=True)
class CitationRecord:
    id: str
    document_id: str
    filename: str
    page_number: int
    passage: str
    section_heading: str | None = None
    score: float | None = None


@dataclass(frozen=True, slots=True)
class GroundedAnswer:
    text: str
    citations: tuple[CitationRecord, ...] = ()
    abstained: bool = False


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    role: Literal["customer", "agent"]
    text: str


@dataclass(frozen=True, slots=True)
class IngestionResult:
    document_id: str
    filename: str
    page_count: int
    chunks: tuple[DocumentChunk, ...]
    warnings: tuple[str, ...] = ()
    metadata: dict[str, str | int | bool] = field(default_factory=dict)
