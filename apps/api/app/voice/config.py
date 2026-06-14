from __future__ import annotations

import os
from dataclasses import dataclass


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if value is None else float(value)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None else int(value)


@dataclass(frozen=True, slots=True)
class VADConfig:
    threshold: float = 0.55
    prefix_padding_ms: int = 300
    silence_duration_ms: int = 700
    barge_in_speech_ms: int = 120
    speaker_tail_ms: int = 80

    @classmethod
    def from_env(cls) -> "VADConfig":
        return cls(
            threshold=_env_float("VOICE_VAD_THRESHOLD", 0.55),
            prefix_padding_ms=_env_int("VOICE_VAD_PREFIX_PADDING_MS", 300),
            silence_duration_ms=_env_int("VOICE_VAD_SILENCE_MS", 700),
            barge_in_speech_ms=_env_int("VOICE_BARGE_IN_SPEECH_MS", 120),
            speaker_tail_ms=_env_int("VOICE_SPEAKER_TAIL_MS", 80),
        )

    def as_client_dict(self) -> dict[str, int | float]:
        return {
            "threshold": self.threshold,
            "prefixPaddingMs": self.prefix_padding_ms,
            "silenceDurationMs": self.silence_duration_ms,
            "bargeInSpeechMs": self.barge_in_speech_ms,
            "speakerTailMs": self.speaker_tail_ms,
        }


@dataclass(frozen=True, slots=True)
class VoiceConfig:
    stt_provider: str = "demo"
    tts_provider: str = "demo"
    audio_sample_rate: int = 24_000
    audio_chunk_bytes: int = 16_384
    tts_voice: str = "coral"
    tts_model: str = "gpt-4o-mini-tts"
    stt_model: str = "gpt-4o-mini-transcribe"
    stt_language: str = "en"
    stt_delay: str = "low"
    max_audio_message_bytes: int = 256_000
    max_tts_segment_chars: int = 180
    vad: VADConfig = VADConfig()

    @classmethod
    def from_env(cls) -> "VoiceConfig":
        return cls(
            stt_provider=os.getenv("STT_PROVIDER", "demo").lower(),
            tts_provider=os.getenv("TTS_PROVIDER", "demo").lower(),
            audio_sample_rate=_env_int("VOICE_SAMPLE_RATE", 24_000),
            audio_chunk_bytes=_env_int("VOICE_AUDIO_CHUNK_BYTES", 16_384),
            tts_voice=os.getenv("TTS_VOICE", "coral"),
            tts_model=os.getenv("TTS_MODEL", "gpt-4o-mini-tts"),
            stt_model=os.getenv("STT_MODEL", "gpt-4o-mini-transcribe"),
            stt_language=os.getenv("STT_LANGUAGE", "en"),
            stt_delay=os.getenv("STT_DELAY", "low"),
            max_audio_message_bytes=_env_int(
                "VOICE_MAX_AUDIO_MESSAGE_BYTES", 256_000
            ),
            max_tts_segment_chars=_env_int("VOICE_TTS_SEGMENT_CHARS", 180),
            vad=VADConfig.from_env(),
        )
