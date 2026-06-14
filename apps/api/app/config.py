from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


# config.py lives at <api>/app/config.py. Locally <api> = apps/api, so the repo
# root is parents[3]; but in the Docker image apps/api is copied to /app, so the
# file is /app/app/config.py and parents[3] would IndexError. Resolve both
# layouts defensively. These paths only locate optional .env files for local
# dev — in the container, env vars are injected by the platform (no .env).
_PARENTS = Path(__file__).resolve().parents
_API_DIR = _PARENTS[1]  # apps/api (local) or /app (container)
REPO_ROOT = _PARENTS[3] if len(_PARENTS) > 3 else _API_DIR

# Provider factories (LLM/TTS/STT/embeddings) read their API keys via
# os.getenv at request time. pydantic-settings only loads .env into Settings,
# not into the process environment, so populate os.environ from any local .env
# at import. load_dotenv on a missing path is a harmless no-op.
_ENV_FILES = (REPO_ROOT / ".env", _API_DIR / ".env")
for _env_file in _ENV_FILES:
    load_dotenv(_env_file)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
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
