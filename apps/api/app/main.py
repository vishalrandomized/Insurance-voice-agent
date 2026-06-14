import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

settings = get_settings()

_background_tasks: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm: ingest the active policy document at startup so the first caller
    # doesn't pay the ~8s cold-start re-ingestion. Runs in the background so
    # /health is immediately available; re-ingestion is lock-guarded so a racing
    # first request won't double-ingest.
    async def _prewarm() -> None:
        try:
            from app.routes.documents import seed_document_if_empty

            # Resolves the active doc if present (e.g. local disk), otherwise
            # ingests the bundled seed PDF so the agent is grounded on a fresh
            # (ephemeral-filesystem) deploy with no manual upload.
            document_id = await seed_document_if_empty()
            print(f"[startup] document pre-warm complete: {document_id}", flush=True)
        except Exception as exc:  # noqa: BLE001 - never block startup
            print(f"[startup] document pre-warm skipped: {exc!r}", flush=True)

    task = asyncio.create_task(_prewarm())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    yield


app = FastAPI(
    title="AssureLine API",
    version="0.1.0",
    description="Document-grounded realtime insurance sales agent.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "assureline-api"}


@app.get("/debug/tts.wav")
async def debug_tts_wav(text: str | None = None):
    """Synthesize TTS and return a standard WAV. Lets a browser play the exact
    agent audio via its native decoder, bypassing the streaming PCM player.
    Open directly, e.g. http://localhost:8000/debug/tts.wav
    """
    import io
    import os
    import wave

    from fastapi import Response

    from app.providers.tts.deepgram import DeepgramTTSProvider

    sample_rate = 24_000
    speech = text or (
        "Hello, this is the AssureLine insurance advisor. "
        "This is a test of the audio playback pipeline. "
        "If you can hear this sentence clearly, your audio output is working."
    )
    provider = DeepgramTTSProvider(
        model=os.getenv("TTS_MODEL", "aura-2-thalia-en"),
        sample_rate=sample_rate,
    )
    pcm = bytearray()
    async for chunk in provider.stream_audio(speech, 1):
        pcm.extend(chunk)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(pcm))
    return Response(content=buffer.getvalue(), media_type="audio/wav")


def _include_optional_routers() -> None:
    try:
        from app.routes.router import router as api_router

        app.include_router(api_router, prefix="/api")
    except ImportError:
        pass

    try:
        from app.websocket.router import router as websocket_router

        app.include_router(websocket_router)
    except ImportError:
        pass


_include_optional_routers()
