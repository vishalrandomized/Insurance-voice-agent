import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.rag.exceptions import DocumentValidationError
from app.rag.service import create_default_service

router = APIRouter(prefix="/documents", tags=["documents"])
rag_service = create_default_service()
_documents: dict[str, dict[str, object]] = {}
_latest_document_id: str | None = None
_latest_document_filename: str | None = None
# Guards re-ingestion so a startup pre-warm and a concurrent first request don't
# both embed the same PDF.
_ingest_lock = asyncio.Lock()
_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
_UPLOADS_DIR = _DATA_DIR / "uploaded_documents"
_ACTIVE_DOCUMENT_PATH = _DATA_DIR / "active_document.json"


@router.post("")
async def upload_document(file: UploadFile = File(...)) -> dict[str, object]:
    global _latest_document_id, _latest_document_filename
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="Only PDF documents are supported")

    document_id = str(uuid4())
    content = await file.read()
    _UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = _UPLOADS_DIR / f"{document_id}.pdf"
    pdf_path.write_bytes(content)
    supabase = await _create_persistent_document(
        document_id, file.filename or "insurance-product.pdf"
    )
    try:
        result = await rag_service.ingest_pdf(
            content,
            filename=file.filename or "insurance-product.pdf",
            document_id=document_id,
        )
    except DocumentValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    record = {
        "documentId": result.document_id,
        "filename": result.filename,
        "status": "ready",
        "pageCount": result.page_count,
        "chunkCount": len(result.chunks),
        "warnings": list(result.warnings),
    }
    _documents[document_id] = record
    _latest_document_id = document_id
    _latest_document_filename = file.filename or "insurance-product.pdf"
    _ACTIVE_DOCUMENT_PATH.write_text(
        json.dumps(
            {
                "documentId": document_id,
                "filename": file.filename or "insurance-product.pdf",
                "pdfPath": str(pdf_path),
            }
        )
    )
    if supabase:
        await supabase.patch(
            "documents",
            params={"id": f"eq.{document_id}"},
            json={
                "status": "ready",
                "page_count": result.page_count,
            },
        )
        await supabase.aclose()
    return record


@router.get("/{document_id}/status")
async def document_status(document_id: str) -> dict[str, object]:
    record = _documents.get(document_id)
    if not record:
        raise HTTPException(status_code=404, detail="Document not found")
    return record


def latest_document_id() -> str | None:
    return os.getenv("DEFAULT_DOCUMENT_ID") or _latest_document_id


async def resolve_active_document_id() -> str | None:
    default_document_id = os.getenv("DEFAULT_DOCUMENT_ID", "").strip()
    if default_document_id:
        return default_document_id

    global _latest_document_id, _latest_document_filename
    if _latest_document_id:
        count = await rag_service.store.count(_latest_document_id)
        if count > 0:
            return _latest_document_id

    if not _ACTIVE_DOCUMENT_PATH.exists():
        return None

    try:
        payload = json.loads(_ACTIVE_DOCUMENT_PATH.read_text())
        document_id = str(payload["documentId"])
        filename = str(payload["filename"])
        pdf_path = Path(str(payload["pdfPath"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

    if not pdf_path.exists():
        return None

    if await rag_service.store.count(document_id) == 0:
        async with _ingest_lock:
            # Re-check inside the lock: another caller (or the startup pre-warm)
            # may have ingested it while we waited.
            if await rag_service.store.count(document_id) == 0:
                content = pdf_path.read_bytes()
                await rag_service.ingest_pdf(
                    content,
                    filename=filename,
                    document_id=document_id,
                )

    _latest_document_id = document_id
    _latest_document_filename = filename
    return document_id


async def seed_document_if_empty() -> str | None:
    """Ground the agent on a bundled seed PDF when no active document exists.

    Railway's filesystem is ephemeral, so uploaded PDFs / active_document.json
    don't survive a restart. This ingests the bundled seed (apps/api/seed/
    policy.pdf, overridable via SEED_DOCUMENT_PATH) at startup so the agent is
    grounded with zero manual upload after every deploy.
    """
    from uuid import NAMESPACE_URL, uuid5

    global _latest_document_id, _latest_document_filename

    existing = await resolve_active_document_id()
    if existing:
        return existing

    seed_str = os.getenv("SEED_DOCUMENT_PATH", "").strip()
    seed_path = (
        Path(seed_str)
        if seed_str
        else Path(__file__).resolve().parents[2] / "seed" / "policy.pdf"
    )
    if not seed_path.exists():
        return None

    document_id = str(uuid5(NAMESPACE_URL, "assureline:seed-document"))
    filename = os.getenv(
        "SEED_DOCUMENT_FILENAME", "Setu_Sampoorna_Prospectus.pdf"
    )
    async with _ingest_lock:
        if await rag_service.store.count(document_id) == 0:
            content = seed_path.read_bytes()
            await rag_service.ingest_pdf(
                content, filename=filename, document_id=document_id
            )
    _latest_document_id = document_id
    _latest_document_filename = filename
    return document_id


def active_policy_name() -> str | None:
    """Human-readable policy name derived from the active document's filename
    (e.g. 'Setu_Sampoorna_Prospectus.md.pdf' -> 'Setu Sampoorna Prospectus').
    Used to personalize the spoken greeting."""
    import re

    name = _latest_document_filename
    if not name and _ACTIVE_DOCUMENT_PATH.exists():
        # Cheap filename read (no re-ingestion) so the greeting can name the
        # policy on a cold start without paying the embedding cost.
        try:
            name = str(json.loads(_ACTIVE_DOCUMENT_PATH.read_text())["filename"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            name = None
    if not name:
        return None
    stem = name
    while True:
        stripped = re.sub(r"\.(pdf|md|txt|docx?)$", "", stem, flags=re.IGNORECASE)
        if stripped == stem:
            break
        stem = stripped
    cleaned = re.sub(r"[._\-]+", " ", stem).strip()
    if not cleaned:
        return None
    # Drop document-type words so "Setu Sampoorna Prospectus" reads as the
    # policy name "Setu Sampoorna".
    stop = {
        "prospectus", "brochure", "policy", "plan", "document", "wording",
        "wordings", "terms", "conditions", "final", "draft", "copy", "v1", "v2",
    }
    words = [w for w in cleaned.split() if w.lower() not in stop]
    if not words:
        words = cleaned.split()
    return " ".join(word.capitalize() for word in words)


async def _create_persistent_document(
    document_id: str, filename: str
) -> httpx.AsyncClient | None:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    product_id = os.getenv("DEFAULT_PRODUCT_ID", "").strip()
    if not (url and key and product_id):
        return None
    client = httpx.AsyncClient(
        base_url=f"{url.rstrip('/')}/rest/v1/",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    response = await client.post(
        "documents",
        headers={"Prefer": "return=minimal"},
        json={
            "id": document_id,
            "product_id": product_id,
            "filename": filename,
            "status": "processing",
        },
    )
    try:
        response.raise_for_status()
    except Exception:
        await client.aclose()
        raise
    return client
