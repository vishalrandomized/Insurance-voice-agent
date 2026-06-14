from __future__ import annotations

import os

from app.voice.config import VoiceConfig

from .base import TTSProvider
from .deepgram import DeepgramTTSProvider
from .demo import DemoTTSProvider
from .openai import OpenAITTSProvider


def create_tts_provider(config: VoiceConfig) -> TTSProvider:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if config.tts_provider == "demo" or (
        config.tts_provider == "openai" and not api_key
    ):
        return DemoTTSProvider(sample_rate=config.audio_sample_rate)
    if config.tts_provider == "deepgram":
        deepgram_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
        if not deepgram_key:
            return DemoTTSProvider(sample_rate=config.audio_sample_rate)
        return DeepgramTTSProvider(
            api_key=deepgram_key,
            model=config.tts_model,
            sample_rate=config.audio_sample_rate,
        )
    if config.tts_provider == "openai":
        return OpenAITTSProvider(
            api_key=api_key,
            model=config.tts_model,
            voice=config.tts_voice,
            sample_rate=config.audio_sample_rate,
        )
    raise ValueError(f"Unsupported TTS provider: {config.tts_provider}")
