from __future__ import annotations

import re
from collections.abc import AsyncIterator

from app.prompts.grounding import (
    ABSTENTION_TEXT,
    OPENING_GREETING,
    SYSTEM_INSTRUCTIONS,
    build_grounded_prompt,
)
from app.providers.embeddings.factory import create_embedding_provider
from app.providers.llm.factory import create_llm_provider
from app.providers.llm.base import LLMProvider

from .ingestion import PDFIngestor
from .models import (
    CitationRecord,
    ConversationMessage,
    GroundedAnswer,
    IngestionResult,
)
from .store import InMemoryVectorStore, SupabaseVectorStore, create_vector_store

CITATION_RE = re.compile(r"\[(C\d+)\]")


class GroundedInsuranceService:
    def __init__(
        self,
        *,
        ingestor: PDFIngestor,
        store: InMemoryVectorStore | SupabaseVectorStore,
        llm: LLMProvider,
        retrieval_top_k: int = 5,
        minimum_score: float = 0.08,
    ) -> None:
        self.ingestor = ingestor
        self.store = store
        self.llm = llm
        self.retrieval_top_k = retrieval_top_k
        self.minimum_score = minimum_score

    async def ingest_pdf(
        self,
        content: bytes,
        *,
        filename: str,
        document_id: str | None = None,
    ) -> IngestionResult:
        result = self.ingestor.ingest_bytes(
            content,
            filename=filename,
            document_id=document_id,
        )
        await self.store.add(result.chunks)
        return result

    async def answer(
        self,
        question: str,
        *,
        document_id: str,
    ) -> GroundedAnswer:
        normalized_question = question.strip()
        if not normalized_question:
            return self._abstention()

        results = await self.store.search(
            normalized_question,
            document_id=document_id,
            top_k=self.retrieval_top_k,
            min_score=self.minimum_score,
        )

        # Always let the model see the message (with evidence if any) so it can
        # answer small talk conversationally, not only factual lookups.
        prompt, citation_map = build_grounded_prompt(normalized_question, results)
        generated = (
            await self.llm.generate(
                instructions=SYSTEM_INSTRUCTIONS,
                prompt=prompt,
            )
        ).strip()
        if not generated or generated == ABSTENTION_TEXT:
            return self._abstention()

        marker_ids = list(dict.fromkeys(CITATION_RE.findall(generated)))
        # A conversational reply (greeting / small talk) carries no citations —
        # accept it as-is.
        if not marker_ids:
            return GroundedAnswer(text=generated, citations=(), abstained=False)
        # A cited answer must reference only real evidence; a marker not present
        # in the evidence is a hallucinated citation, so abstain.
        if any(marker not in citation_map for marker in marker_ids):
            return self._abstention()

        citations = tuple(
            CitationRecord(
                id=citation_map[marker].chunk.id,
                document_id=citation_map[marker].chunk.document_id,
                filename=citation_map[marker].chunk.filename,
                page_number=citation_map[marker].chunk.page_number,
                section_heading=citation_map[marker].chunk.section_heading,
                passage=citation_map[marker].chunk.text,
                score=citation_map[marker].score,
            )
            for marker in marker_ids
        )
        return GroundedAnswer(text=generated, citations=citations, abstained=False)

    async def pitch(self, *, policy_name: str | None = None) -> GroundedAnswer:
        """Return the hardcoded spoken opener (OPENING_GREETING in
        prompts/grounding.py), with the policy name filled in. No LLM and no
        retrieval — instant and deterministic, so the call starts immediately."""
        phrase = f"the {policy_name} plan" if policy_name else "this policy"
        return GroundedAnswer(
            text=OPENING_GREETING.replace("{policy}", phrase),
            citations=(),
            abstained=False,
        )

    async def stream_answer(
        self,
        question: str,
        *,
        document_id: str,
        chunk_size: int = 80,
    ) -> AsyncIterator[str]:
        """Stream only after grounding verification so unsafe text is never emitted."""
        answer = await self.answer(question, document_id=document_id)
        for start in range(0, len(answer.text), chunk_size):
            yield answer.text[start : start + chunk_size]

    async def summarize_conversation(
        self,
        messages: list[ConversationMessage],
    ) -> str:
        return (await self.llm.summarize(messages)).strip()

    @staticmethod
    def _abstention() -> GroundedAnswer:
        return GroundedAnswer(
            text=ABSTENTION_TEXT,
            citations=(),
            abstained=True,
        )


def create_default_service() -> GroundedInsuranceService:
    """Build a local-first service from environment-configured providers."""
    import os

    from .ingestion import PDFIngestionConfig

    app_settings = None
    try:
        from app.config import get_settings

        app_settings = get_settings()
    except (ImportError, ModuleNotFoundError):
        pass

    max_pdf_size_mb = int(
        os.getenv(
            "MAX_PDF_SIZE_MB",
            str(getattr(app_settings, "max_pdf_size_mb", 20)),
        )
    )
    max_pdf_pages = int(
        os.getenv(
            "MAX_PDF_PAGES",
            str(getattr(app_settings, "max_pdf_pages", 250)),
        )
    )
    config = PDFIngestionConfig(
        max_size_bytes=max_pdf_size_mb * 1024 * 1024,
        max_pages=max_pdf_pages,
        target_chunk_tokens=int(os.getenv("RAG_CHUNK_TOKENS", "700")),
        overlap_tokens=int(os.getenv("RAG_CHUNK_OVERLAP", "100")),
    )
    llm_provider = os.getenv("LLM_PROVIDER") or getattr(
        app_settings, "llm_provider", "local"
    )
    embedding_provider = os.getenv("EMBEDDING_PROVIDER", "local")
    openai_key = os.getenv("OPENAI_API_KEY") or getattr(
        app_settings, "openai_api_key", None
    )
    gemini_key = os.getenv("GEMINI_API_KEY")
    if llm_provider.lower() == "openai" and not openai_key:
        llm_provider = "local"
    if llm_provider.lower() == "gemini" and not gemini_key:
        llm_provider = "local"
    if embedding_provider.lower() == "openai" and not openai_key:
        embedding_provider = "local"
    if embedding_provider.lower() == "gemini" and not gemini_key:
        embedding_provider = "local"
    llm_model = os.getenv("LLM_MODEL") or getattr(
        app_settings, "llm_model", None
    )
    embeddings = create_embedding_provider(provider=embedding_provider)
    llm = create_llm_provider(llm_provider, model=llm_model)
    # Remote providers can hit rate limits (Gemini 429) or transient 5xx — wrap
    # them so a failed call degrades to the offline extractive provider for that
    # turn instead of erroring the whole session.
    if llm_provider.lower() in {"gemini", "openai"}:
        from app.providers.llm.fallback import FallbackLLMProvider

        llm = FallbackLLMProvider(llm)
    return GroundedInsuranceService(
        ingestor=PDFIngestor(config),
        store=create_vector_store(embeddings),
        llm=llm,
        retrieval_top_k=int(os.getenv("RAG_TOP_K", "5")),
        minimum_score=float(os.getenv("RAG_MIN_SCORE", "0.08")),
    )
