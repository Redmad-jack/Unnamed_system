from __future__ import annotations

from conscious_entity.audio.config import (
    DEFAULT_STT_ENDPOINT,
    DEFAULT_TTS_ENDPOINT,
    AudioConfig,
)


def _deps_available(self):
    return {"available": True, "missing": [], "websockets": "available"}


def test_audio_config_disabled_without_provider(monkeypatch):
    monkeypatch.delenv("ENTITY_AUDIO_PROVIDER", raising=False)
    monkeypatch.delenv("ENTITY_AUDIO_ENABLED", raising=False)

    config = AudioConfig.from_env()

    assert config.disabled_reason() == "audio_provider_disabled"
    assert config.to_public_dict()["enabled"] is False


def test_audio_config_missing_credentials(monkeypatch):
    monkeypatch.setattr(AudioConfig, "dependency_status", _deps_available)
    monkeypatch.setenv("ENTITY_AUDIO_PROVIDER", "volcengine")
    monkeypatch.setenv("ENTITY_AUDIO_ENABLED", "1")
    monkeypatch.delenv("ENTITY_VOLCENGINE_API_KEY", raising=False)
    monkeypatch.delenv("ENTITY_VOLCENGINE_APP_ID", raising=False)
    monkeypatch.delenv("ENTITY_VOLCENGINE_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("ENTITY_VOLCENGINE_TTS_VOICE_TYPE", "voice")

    config = AudioConfig.from_env()

    assert config.disabled_reason() == "missing_volcengine_credentials"


def test_audio_config_api_key_auth_and_defaults(monkeypatch):
    monkeypatch.setattr(AudioConfig, "dependency_status", _deps_available)
    monkeypatch.setenv("ENTITY_AUDIO_PROVIDER", "volcengine")
    monkeypatch.setenv("ENTITY_AUDIO_ENABLED", "1")
    monkeypatch.setenv("ENTITY_VOLCENGINE_API_KEY", "secret-api-key-value")
    monkeypatch.setenv("ENTITY_VOLCENGINE_TTS_VOICE_TYPE", "voice")

    config = AudioConfig.from_env()
    public = config.to_public_dict()

    assert config.disabled_reason() is None
    assert config.stt_endpoint == DEFAULT_STT_ENDPOINT
    assert config.tts_endpoint == DEFAULT_TTS_ENDPOINT
    assert config.tts_sample_rate == 24000
    assert public["auth"]["api_key"] != "secret-api-key-value"
    assert "secret-api-key-value" not in str(public)
    assert public["tts"]["sample_rate"] == 24000


def test_audio_config_app_token_fallback_auth(monkeypatch):
    monkeypatch.setattr(AudioConfig, "dependency_status", _deps_available)
    monkeypatch.setenv("ENTITY_AUDIO_PROVIDER", "volcengine")
    monkeypatch.setenv("ENTITY_AUDIO_ENABLED", "1")
    monkeypatch.delenv("ENTITY_VOLCENGINE_API_KEY", raising=False)
    monkeypatch.setenv("ENTITY_VOLCENGINE_APP_ID", "app-id-secret")
    monkeypatch.setenv("ENTITY_VOLCENGINE_ACCESS_TOKEN", "access-token-secret")
    monkeypatch.setenv("ENTITY_VOLCENGINE_TTS_VOICE_TYPE", "voice")

    config = AudioConfig.from_env()
    public = config.to_public_dict()

    assert config.disabled_reason() is None
    assert public["auth"]["mode"] == "app_token"
    assert "access-token-secret" not in str(public)


def test_audio_config_voice_type_required_for_tts(monkeypatch):
    monkeypatch.setattr(AudioConfig, "dependency_status", _deps_available)
    monkeypatch.setenv("ENTITY_AUDIO_PROVIDER", "volcengine")
    monkeypatch.setenv("ENTITY_AUDIO_ENABLED", "1")
    monkeypatch.setenv("ENTITY_VOLCENGINE_API_KEY", "secret")
    monkeypatch.delenv("ENTITY_VOLCENGINE_TTS_VOICE_TYPE", raising=False)

    config = AudioConfig.from_env()

    assert config.disabled_reason() == "missing_tts_voice_type"
