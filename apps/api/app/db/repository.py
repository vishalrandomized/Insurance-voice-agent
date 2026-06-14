from __future__ import annotations

import os

from .base import Repository
from .memory import InMemoryRepository
from .supabase import SupabaseRestRepository

_repository: Repository | None = None


def get_repository() -> Repository:
    global _repository
    if _repository is None:
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if url and key:
            _repository = SupabaseRestRepository(url, key)
        else:
            _repository = InMemoryRepository()
    return _repository


def reset_repository(repository: Repository | None = None) -> None:
    """Replace the singleton; primarily useful for isolated application tests."""
    global _repository
    _repository = repository
