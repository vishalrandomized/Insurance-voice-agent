from __future__ import annotations

import os

from app.voice.config import VoiceConfig

from .assemblyai import AssemblyAIStreamingSTTProvider
from .base import STTProvider
from .demo import DemoSTTProvider
from .openai import OpenAIRealtimeSTTProvider


def create_stt_provider(config: VoiceConfig) -> STTProvider:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if config.stt_provider == "demo" or (
        config.stt_provider == "openai" and not api_key
    ):
        return DemoSTTProvider()
    if config.stt_provider == "assemblyai":
        assemblyai_key = os.getenv("ASSEMBLYAI_API_KEY", "").strip()
        if not assemblyai_key:
            raise ValueError(
                "ASSEMBLYAI_API_KEY is required when STT_PROVIDER=assemblyai"
            )
        return AssemblyAIStreamingSTTProvider(
            api_key=assemblyai_key,
            model=config.stt_model,
            sample_rate=config.audio_sample_rate,
        )
    if config.stt_provider == "openai":
        return OpenAIRealtimeSTTProvider(
            api_key=api_key,
            model=config.stt_model,
            language=config.stt_language,
            delay=config.stt_delay,
            sample_rate=config.audio_sample_rate,
        )
    raise ValueError(f"Unsupported STT provider: {config.stt_provider}")
