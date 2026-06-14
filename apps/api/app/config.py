from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[3]

# Provider factories (LLM/TTS/STT/embeddings) read their API keys via
# os.getenv at request time. pydantic-settings only loads .env into Settings,
# not into the process environment, so without this the keys are invisible to
# those factories and they silently fall back to the demo/local providers
# (e.g. demo TTS emits 440 Hz beeps instead of speech). Populate os.environ
# from .env at import so every os.getenv lookup sees the real keys.
load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "apps" / "api" / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / "apps" / "api" / ".env"),
        extra="ignore",
    )

    frontend_origin: str = "http://localhost:3000"
    openai_api_key: str | None = None
    llm_provider: str = "gemini"
    stt_provider: str = "assemblyai"
    tts_provider: str = "deepgram"
    llm_model: str = "gemini-2.5-flash"
    stt_model: str = "u3-rt-pro"
    tts_model: str = "aura-2-thalia-en"
    database_url: str | None = None
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    max_pdf_size_mb: int = 20
    max_pdf_pages: int = 250


@lru_cache
def get_settings() -> Settings:
    return Settings()
