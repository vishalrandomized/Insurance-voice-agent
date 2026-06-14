"""Document ingestion, retrieval, and grounded generation services.

Imports are resolved lazily to keep provider modules free of package import cycles.
"""

from importlib import import_module
from typing import Any

_EXPORTS = {
    "CitationRecord": ("app.rag.models", "CitationRecord"),
    "ConversationMessage": ("app.rag.models", "ConversationMessage"),
    "DocumentChunk": ("app.rag.models", "DocumentChunk"),
    "GroundedAnswer": ("app.rag.models", "GroundedAnswer"),
    "GroundedInsuranceService": (
        "app.rag.service",
        "GroundedInsuranceService",
    ),
    "InMemoryVectorStore": ("app.rag.store", "InMemoryVectorStore"),
    "IngestionResult": ("app.rag.models", "IngestionResult"),
    "PDFIngestionConfig": ("app.rag.ingestion", "PDFIngestionConfig"),
    "PDFIngestor": ("app.rag.ingestion", "PDFIngestor"),
    "RetrievalResult": ("app.rag.models", "RetrievalResult"),
    "create_default_service": ("app.rag.service", "create_default_service"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
