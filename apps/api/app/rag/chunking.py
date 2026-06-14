from __future__ import annotations

import re
from collections.abc import Iterable
from uuid import uuid4

from .models import DocumentChunk, DocumentPage

TOKEN_RE = re.compile(r"\S+")
HEADING_RE = re.compile(r"^[A-Z][A-Z0-9 &(),:/.'-]{3,100}$")


def _token_spans(text: str) -> list[tuple[int, int]]:
    return [(match.start(), match.end()) for match in TOKEN_RE.finditer(text)]


def _heading_before(text: str, position: int) -> str | None:
    if position == 0:
        first_line_end = text.find("\n")
        prefix = text if first_line_end == -1 else text[:first_line_end]
    else:
        prefix = text[:position]
    for line in reversed(prefix.splitlines()):
        candidate = " ".join(line.split()).strip(" :-")
        if not candidate or len(candidate) > 100:
            continue
        if HEADING_RE.fullmatch(candidate) or (
            len(candidate.split()) <= 10
            and candidate[:1].isupper()
            and not candidate.endswith((".", ";", ","))
        ):
            return candidate
    return None


def chunk_pages(
    pages: Iterable[DocumentPage],
    *,
    target_tokens: int = 700,
    overlap_tokens: int = 100,
) -> list[DocumentChunk]:
    if target_tokens < 50:
        raise ValueError("target_tokens must be at least 50")
    if overlap_tokens < 0 or overlap_tokens >= target_tokens:
        raise ValueError("overlap_tokens must be between 0 and target_tokens")

    chunks: list[DocumentChunk] = []
    step = target_tokens - overlap_tokens
    for page in pages:
        text = page.text.strip()
        spans = _token_spans(text)
        if not spans:
            continue

        page_chunk_index = 0
        for start_token in range(0, len(spans), step):
            end_token = min(start_token + target_tokens, len(spans))
            start_char = spans[start_token][0]
            end_char = spans[end_token - 1][1]
            chunk_text = text[start_char:end_char].strip()
            if not chunk_text:
                continue
            chunks.append(
                DocumentChunk(
                    id=str(uuid4()),
                    document_id=page.document_id,
                    filename=page.filename,
                    page_number=page.page_number,
                    chunk_index=page_chunk_index,
                    text=chunk_text,
                    section_heading=_heading_before(text, start_char),
                )
            )
            page_chunk_index += 1
            if end_token == len(spans):
                break
    return chunks
