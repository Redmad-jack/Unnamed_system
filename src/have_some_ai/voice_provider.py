from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from have_some_ai.doubao.tts_bidirectional_client import doubao_tts_speakers_from_env


@dataclass(frozen=True)
class VoiceProviderConfig:
    provider: str
    stt_mode: str
    voice_base_url: str | None
    stt_model: str
    tts_model: str
    tts_voice: str
    stt_language: str | None
    conversation_stream_available: bool = False
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
            "conversation_stream_available": self.conversation_stream_available,
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
        conversation_stream_available=(provider == "doubao" and stt_mode == "asr_tts_stream"),
        input_audio_format=(
            "pcm_s16le" if provider == "doubao" and stt_mode == "asr_tts_stream" else None
        ),
        input_sample_rate=(
            _doubao_asr_sample_rate() if provider == "doubao" and stt_mode == "asr_tts_stream" else None
        ),
        output_audio_format=(
            "pcm_s16le" if provider == "doubao" and stt_mode == "asr_tts_stream" else None
        ),
        output_sample_rate=(
            _doubao_tts_sample_rate()
            if provider == "doubao" and stt_mode == "asr_tts_stream"
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
        return "asr_tts_stream"
    if provider in {"aihubmix", "openai"}:
        return "file"
    return "file"


def _default_stt_model(provider: str, stt_mode: str) -> str:
    if provider == "doubao":
        return "doubao-asr-bigmodel-async"
    if provider == "aihubmix" or stt_mode == "file":
        return "whisper-large-v3"
    return "gpt-4o-mini-transcribe"


def _doubao_asr_sample_rate() -> int:
    value = os.getenv("DOUBAO_ASR_SAMPLE_RATE", "16000")
    try:
        return int(value)
    except ValueError:
        return 16000


def _doubao_tts_sample_rate() -> int:
    value = os.getenv("DOUBAO_TTS_SAMPLE_RATE", "24000")
    try:
        return int(value)
    except ValueError:
        return 24000


def _provider_capabilities(provider: str, stt_mode: str) -> dict[str, Any]:
    if provider == "doubao" and stt_mode == "asr_tts_stream":
        asr_ready = _doubao_asr_credentials_configured()
        tts_ready = _doubao_tts_credentials_configured()
        return {
            "audio_input": True,
            "audio_output": True,
            "structured_answer": False,
            "credentials_configured": asr_ready and tts_ready,
            "asr_credentials_configured": asr_ready,
            "tts_credentials_configured": tts_ready,
            "asr_endpoint": os.getenv(
                "DOUBAO_ASR_ENDPOINT",
                "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async",
            ),
            "asr_resource_id": os.getenv(
                "DOUBAO_ASR_RESOURCE_ID",
                "volc.seedasr.sauc.duration",
            ),
            "tts_endpoint": os.getenv(
                "DOUBAO_TTS_ENDPOINT",
                "wss://openspeech.bytedance.com/api/v3/tts/bidirection",
            ),
            "tts_resource_id": os.getenv("DOUBAO_TTS_RESOURCE_ID", "seed-icl-2.0"),
            "speakers": doubao_tts_speakers_from_env(),
            "default_speaker_language": "zh",
        }
    return {}


def _doubao_asr_credentials_configured() -> bool:
    return bool(os.getenv("DOUBAO_ASR_API_KEY") or os.getenv("DOUBAO_API_KEY"))


def _doubao_tts_credentials_configured() -> bool:
    return bool(os.getenv("DOUBAO_TTS_API_KEY") or os.getenv("DOUBAO_API_KEY"))
