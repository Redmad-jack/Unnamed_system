from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


_DEFAULT_DOUBAO_APP_KEY = "PlgvMymc7f3tQnJ6"


@dataclass(frozen=True)
class VoiceProviderConfig:
    provider: str
    stt_mode: str
    voice_base_url: str | None
    stt_model: str
    tts_model: str
    tts_voice: str
    stt_language: str | None
    conversation_realtime_available: bool = False
    realtime_transport: str | None = None
    input_audio_format: str | None = None
    input_sample_rate: int | None = None
    output_audio_format: str | None = None
    output_sample_rate: int | None = None
    provider_capabilities: dict[str, Any] | None = None

    def public_data(self) -> dict[str, Any]:
        capabilities = self.provider_capabilities or {}
        sample_rate = self.input_sample_rate
        return {
            "provider": self.provider,
            "stt_mode": self.stt_mode,
            "voice_base_url": self.voice_base_url,
            "stt_model": self.stt_model,
            "tts_model": self.tts_model,
            "tts_voice": self.tts_voice,
            "stt_language": self.stt_language,
            "file_stt_available": self.stt_mode in {"file", "auto"},
            "realtime_available": self.stt_mode in {"realtime", "auto"},
            "conversation_realtime_available": self.conversation_realtime_available,
            "realtime_transport": self.realtime_transport,
            "input_audio_format": self.input_audio_format,
            "input_sample_rate": self.input_sample_rate,
            "output_audio_format": self.output_audio_format,
            "output_sample_rate": self.output_sample_rate,
            "sample_rate": sample_rate,
            "provider_capabilities": capabilities,
        }


def resolve_voice_provider_config() -> VoiceProviderConfig:
    base_url = os.getenv("HAVE_SOME_AI_VOICE_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    provider = (os.getenv("HAVE_SOME_AI_VOICE_PROVIDER") or _infer_provider(base_url)).lower()
    stt_mode = (os.getenv("HAVE_SOME_AI_STT_MODE") or _default_stt_mode(provider)).lower()
    language = os.getenv("HAVE_SOME_AI_STT_LANGUAGE")
    language = language.strip() if language and language.strip() else None
    return VoiceProviderConfig(
        provider=provider,
        stt_mode=stt_mode,
        voice_base_url=base_url.rstrip("/") if base_url else None,
        stt_model=os.getenv("HAVE_SOME_AI_STT_MODEL", _default_stt_model(provider, stt_mode)),
        tts_model=os.getenv("HAVE_SOME_AI_TTS_MODEL", "gpt-4o-mini-tts"),
        tts_voice=os.getenv("HAVE_SOME_AI_TTS_VOICE", "alloy"),
        stt_language=language,
        conversation_realtime_available=(
            provider == "doubao" and stt_mode == "realtime_dialogue"
        ),
        realtime_transport=(
            "backend_websocket"
            if provider == "doubao" and stt_mode == "realtime_dialogue"
            else None
        ),
        input_audio_format=(
            "pcm_s16le" if provider == "doubao" and stt_mode == "realtime_dialogue" else None
        ),
        input_sample_rate=(
            _doubao_sample_rate() if provider == "doubao" and stt_mode == "realtime_dialogue" else None
        ),
        output_audio_format=(
            "pcm_s16le" if provider == "doubao" and stt_mode == "realtime_dialogue" else None
        ),
        output_sample_rate=(
            _doubao_output_sample_rate()
            if provider == "doubao" and stt_mode == "realtime_dialogue"
            else None
        ),
        provider_capabilities=_provider_capabilities(provider, stt_mode),
    )


def _infer_provider(base_url: str | None) -> str:
    if base_url and "aihubmix" in base_url.lower():
        return "aihubmix"
    return "openai"


def _default_stt_mode(provider: str) -> str:
    if provider == "doubao":
        return "realtime_dialogue"
    if provider == "aihubmix":
        return "file"
    return "realtime"


def _default_stt_model(provider: str, stt_mode: str) -> str:
    if provider == "doubao":
        return "doubao-realtime-dialogue"
    if provider == "aihubmix" or stt_mode == "file":
        return "whisper-large-v3"
    return "gpt-4o-mini-transcribe"


def _doubao_sample_rate() -> int:
    value = os.getenv("HAVE_SOME_AI_DOUBAO_SAMPLE_RATE", "16000")
    try:
        return int(value)
    except ValueError:
        return 16000


def _doubao_output_sample_rate() -> int:
    value = os.getenv("HAVE_SOME_AI_DOUBAO_OUTPUT_SAMPLE_RATE", "24000")
    try:
        return int(value)
    except ValueError:
        return 24000


def _provider_capabilities(provider: str, stt_mode: str) -> dict[str, Any]:
    if provider == "doubao" and stt_mode == "realtime_dialogue":
        return {
            "audio_input": True,
            "audio_output": True,
            "structured_answer": False,
            "credentials_configured": _doubao_credentials_configured(),
            "dialog_model": os.getenv("HAVE_SOME_AI_DOUBAO_MODEL", "1.2.1.1"),
            "speaker": os.getenv(
                "HAVE_SOME_AI_DOUBAO_SPEAKER",
                "zh_female_vv_jupiter_bigtts",
            ),
        }
    return {}


def _doubao_credentials_configured() -> bool:
    app_key = os.getenv("HAVE_SOME_AI_DOUBAO_APP_KEY", _DEFAULT_DOUBAO_APP_KEY)
    return all(
        (
            os.getenv("HAVE_SOME_AI_DOUBAO_APP_ID"),
            app_key,
            os.getenv("HAVE_SOME_AI_DOUBAO_ACCESS_TOKEN"),
        )
    )
