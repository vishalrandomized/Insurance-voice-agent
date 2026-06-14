from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .chunking import chunk_pages
from .exceptions import DependencyUnavailableError, DocumentValidationError
from .models import DocumentPage, IngestionResult

INSURANCE_TERMS = {
    "insurance",
    "insured",
    "policy",
    "premium",
    "coverage",
    "claim",
    "exclusion",
    "benefit",
    "sum insured",
    "waiting period",
    "policyholder",
}


@dataclass(frozen=True, slots=True)
class PDFIngestionConfig:
    max_size_bytes: int = 20 * 1024 * 1024
    max_pages: int = 250
    min_extractable_characters: int = 100
    target_chunk_tokens: int = 700
    overlap_tokens: int = 100


class PDFIngestor:
    def __init__(self, config: PDFIngestionConfig | None = None) -> None:
        self.config = config or PDFIngestionConfig()

    def ingest_path(
        self,
        path: str | Path,
        *,
        document_id: str | None = None,
    ) -> IngestionResult:
        pdf_path = Path(path)
        if pdf_path.suffix.lower() != ".pdf":
            raise DocumentValidationError("Only PDF documents are supported.")
        return self.ingest_bytes(
            pdf_path.read_bytes(),
            filename=pdf_path.name,
            document_id=document_id,
        )

    def ingest_bytes(
        self,
        content: bytes,
        *,
        filename: str,
        document_id: str | None = None,
    ) -> IngestionResult:
        if not filename.lower().endswith(".pdf"):
            raise DocumentValidationError("Only PDF documents are supported.")
        if not content.startswith(b"%PDF"):
            raise DocumentValidationError("The uploaded file is not a valid PDF.")
        if len(content) > self.config.max_size_bytes:
            max_mb = self.config.max_size_bytes // (1024 * 1024)
            raise DocumentValidationError(f"PDF exceeds the {max_mb} MB size limit.")

        try:
            import fitz
        except ImportError as exc:
            raise DependencyUnavailableError(
                "PyMuPDF is required for PDF ingestion. Install the 'pymupdf' package."
            ) from exc

        resolved_document_id = document_id or str(uuid4())
        try:
            pdf = fitz.open(stream=content, filetype="pdf")
        except Exception as exc:
            raise DocumentValidationError("The PDF is corrupt or unreadable.") from exc

        try:
            if pdf.needs_pass:
                raise DocumentValidationError("Encrypted PDFs are not supported.")
            if pdf.page_count > self.config.max_pages:
                raise DocumentValidationError(
                    f"PDF exceeds the {self.config.max_pages}-page limit."
                )
            if pdf.page_count == 0:
                raise DocumentValidationError("The PDF contains no pages.")

            pages: list[DocumentPage] = []
            for index, page in enumerate(pdf):
                text = page.get_text("text", sort=True)
                normalized = "\n".join(
                    line.rstrip() for line in text.replace("\x00", "").splitlines()
                ).strip()
                pages.append(
                    DocumentPage(
                        document_id=resolved_document_id,
                        filename=filename,
                        page_number=index + 1,
                        text=normalized,
                    )
                )
        finally:
            pdf.close()

        combined_text = "\n".join(page.text for page in pages)
        if len(combined_text.strip()) < self.config.min_extractable_characters:
            raise DocumentValidationError(
                "The PDF has too little extractable text. Scanned PDFs require OCR first."
            )

        chunks = chunk_pages(
            pages,
            target_tokens=self.config.target_chunk_tokens,
            overlap_tokens=self.config.overlap_tokens,
        )
        if not chunks:
            raise DocumentValidationError("No searchable text chunks could be created.")

        lowered = combined_text.lower()
        matched_terms = sorted(term for term in INSURANCE_TERMS if term in lowered)
        warnings: list[str] = []
        if len(matched_terms) < 2:
            warnings.append(
                "The document does not appear to be an insurance product document."
            )

        return IngestionResult(
            document_id=resolved_document_id,
            filename=filename,
            page_count=len(pages),
            chunks=tuple(chunks),
            warnings=tuple(warnings),
            metadata={
                "size_bytes": len(content),
                "insurance_term_matches": len(matched_terms),
            },
        )
