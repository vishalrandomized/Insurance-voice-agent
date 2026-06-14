import asyncio
from collections.abc import AsyncIterator

import fitz

from app.providers.embeddings.local import HashingEmbeddingProvider
from app.providers.llm.local import ExtractiveLLMProvider
from app.providers.stt.demo import DemoSTTProvider
from app.providers.tts.base import TTSProvider
from app.rag.ingestion import PDFIngestionConfig, PDFIngestor
from app.rag.service import GroundedInsuranceService
from app.rag.store import InMemoryVectorStore
from app.voice.config import VoiceConfig
from app.voice.orchestrator import ResponseDelta, VoiceOrchestrator


def _policy_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "Coverage\nHospitalization expenses are covered after a 30 day waiting period.",
    )
    content = document.tobytes()
    document.close()
    return content


async def test_grounded_answers_include_page_citation_and_abstain() -> None:
    service = GroundedInsuranceService(
        ingestor=PDFIngestor(
            PDFIngestionConfig(
                max_size_bytes=1_000_000,
                max_pages=10,
                min_extractable_characters=20,
                target_chunk_tokens=120,
                overlap_tokens=20,
            )
        ),
        store=InMemoryVectorStore(HashingEmbeddingProvider()),
        llm=ExtractiveLLMProvider(),
        minimum_score=0.01,
    )
    result = await service.ingest_pdf(
        _policy_pdf(), filename="policy.pdf", document_id="policy-1"
    )

    answer = await service.answer(
        "What is the hospitalization waiting period?",
        document_id=result.document_id,
    )
    missing = await service.answer(
        "What is the premium amount?",
        document_id="unknown-document",
    )

    assert not answer.abstained
    assert answer.citations[0].page_number == 1
    assert answer.citations[0].filename == "policy.pdf"
    assert missing.abstained


async def test_policy_pitch_is_grounded_and_cited() -> None:
    service = GroundedInsuranceService(
        ingestor=PDFIngestor(
            PDFIngestionConfig(
                max_size_bytes=1_000_000,
                max_pages=10,
                min_extractable_characters=20,
                target_chunk_tokens=120,
                overlap_tokens=20,
            )
        ),
        store=InMemoryVectorStore(HashingEmbeddingProvider()),
        llm=ExtractiveLLMProvider(),
        minimum_score=0.01,
    )
    result = await service.ingest_pdf(
        _policy_pdf(), filename="policy.pdf", document_id="policy-2"
    )

    pitch = await service.pitch(document_id=result.document_id)

    assert not pitch.abstained
    assert pitch.citations
    assert pitch.citations[0].page_number == 1


class SlowTTS(TTSProvider):
    async def stream_audio(
        self, text: str, generation_id: int
    ) -> AsyncIterator[bytes]:
        del text, generation_id
        await asyncio.sleep(0.05)
        yield b"late-audio"


async def _slow_response(transcript, context):
    del transcript, context
    yield ResponseDelta(text="This answer should be interrupted.")


async def test_barge_in_drops_late_audio_from_cancelled_generation() -> None:
    events: list[dict] = []
    orchestrator = VoiceOrchestrator(
        session_id="session-1",
        stt=DemoSTTProvider(),
        tts=SlowTTS(),
        response_stream=_slow_response,
        send_event=lambda event: _record(events, event),
        config=VoiceConfig(),
    )
    await orchestrator.start()
    await orchestrator.submit_text("Explain coverage")
    cancelled_generation = orchestrator.generation_id
    await asyncio.sleep(0.005)
    await orchestrator.cancel_response(cancelled_generation)
    await asyncio.sleep(0.07)
    await orchestrator.close()

    assert any(event["type"] == "agent.response.cancelled" for event in events)
    assert not any(event["type"] == "agent.audio.chunk" for event in events)


async def _record(events: list[dict], event: dict) -> None:
    events.append(event)


class AbstainingLLMProvider:
    async def generate(self, *, instructions: str, prompt: str) -> str:
        del instructions, prompt
        return (
            "I could not find that information in the uploaded insurance product document."
        )

    async def summarize(self, messages):
        del messages
        return "No substantive conversation was recorded."


async def test_policy_pitch_falls_back_to_extractive_summary_when_model_abstains() -> None:
    service = GroundedInsuranceService(
        ingestor=PDFIngestor(
            PDFIngestionConfig(
                max_size_bytes=1_000_000,
                max_pages=10,
                min_extractable_characters=20,
                target_chunk_tokens=120,
                overlap_tokens=20,
            )
        ),
        store=InMemoryVectorStore(HashingEmbeddingProvider()),
        llm=AbstainingLLMProvider(),
        minimum_score=0.01,
    )
    result = await service.ingest_pdf(
        _policy_pdf(), filename="policy.pdf", document_id="policy-3"
    )

    pitch = await service.pitch(document_id=result.document_id)

    assert not pitch.abstained
    assert pitch.citations
    assert "According to the product document" in pitch.text
