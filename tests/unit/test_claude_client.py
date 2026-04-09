"""
test_claude_client.py — configuration contract tests for ClaudeClient.
"""

from __future__ import annotations

import sys
import types

import pytest

from conscious_entity.llm.claude_client import (
    ClaudeClient,
    ClaudeConfigurationError,
)


class _FakeAnthropic:
    last_init_kwargs: dict | None = None

    def __init__(self, **kwargs):
        type(self).last_init_kwargs = kwargs
        self.messages = types.SimpleNamespace(
            create=lambda **_: types.SimpleNamespace(
                content=[types.SimpleNamespace(text="mock response")]
            )
        )


@pytest.fixture(autouse=True)
def clear_llm_env(monkeypatch):
    for key in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ENTITY_LLM_MODEL",
        "ENTITY_LLM_MESSAGES_ENDPOINT",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def fake_anthropic(monkeypatch):
    module = types.ModuleType("anthropic")
    module.Anthropic = _FakeAnthropic
    _FakeAnthropic.last_init_kwargs = None
    monkeypatch.setitem(sys.modules, "anthropic", module)
    return _FakeAnthropic


class _FakeHTTPResponse:
    def __init__(self, payload=None, text: str = "", status_code: int = 200):
        self._payload = payload
        self.text = text
        self.status_code = status_code
        self.headers = {"content-type": "application/json"}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeHTTPClient:
    calls: list[dict] = []
    response: _FakeHTTPResponse | None = None

    def __init__(self, *args, **kwargs):
        type(self).calls = []

    def post(self, url, headers=None, json=None):
        type(self).calls.append({"url": url, "headers": headers or {}, "json": json or {}})
        assert type(self).response is not None
        return type(self).response


@pytest.fixture
def fake_http_client(monkeypatch):
    from conscious_entity.llm import claude_client as module

    _FakeHTTPClient.calls = []
    _FakeHTTPClient.response = _FakeHTTPResponse(
        payload={"content": [{"type": "text", "text": "endpoint response"}]}
    )
    monkeypatch.setattr(module.httpx, "Client", _FakeHTTPClient)
    return _FakeHTTPClient


class TestClaudeClientConfig:
    def test_supplier_mode_uses_auth_token_and_base_url(self, monkeypatch, fake_anthropic):
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "supplier-token")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://provider.example/anthropic")
        monkeypatch.setenv("ENTITY_LLM_MODEL", "provider-custom-model")

        client = ClaudeClient()

        assert client._model == "provider-custom-model"
        assert fake_anthropic.last_init_kwargs == {
            "api_key": None,
            "auth_token": "supplier-token",
            "base_url": "https://provider.example/anthropic",
        }

    def test_official_mode_uses_api_key_and_default_model(self, monkeypatch, fake_anthropic):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "official-key")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy.example/anthropic")

        client = ClaudeClient()

        assert client._model == "claude-sonnet-4-6"
        assert fake_anthropic.last_init_kwargs == {
            "api_key": "official-key",
            "auth_token": None,
            "base_url": "https://proxy.example/anthropic",
        }

    def test_explicit_model_overrides_environment_model(self, monkeypatch, fake_anthropic):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "official-key")
        monkeypatch.setenv("ENTITY_LLM_MODEL", "env-model")

        client = ClaudeClient(model="explicit-model")

        assert client._model == "explicit-model"
        assert fake_anthropic.last_init_kwargs == {
            "api_key": "official-key",
            "auth_token": None,
            "base_url": None,
        }

    def test_missing_supplier_model_raises_clear_error(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "supplier-token")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://provider.example/anthropic")

        with pytest.raises(ClaudeConfigurationError, match="ENTITY_LLM_MODEL"):
            ClaudeClient.resolve_config()

    def test_missing_credentials_raises_clear_error(self):
        with pytest.raises(ClaudeConfigurationError, match="Missing LLM credentials"):
            ClaudeClient.resolve_config()

    def test_custom_messages_endpoint_allows_supplier_mode_without_base_url(
        self,
        monkeypatch,
        fake_anthropic,
    ):
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "supplier-token")
        monkeypatch.setenv("ENTITY_LLM_MODEL", "provider-custom-model")
        monkeypatch.setenv("ENTITY_LLM_MESSAGES_ENDPOINT", "https://provider.example/custom/messages")

        config = ClaudeClient.resolve_config()

        assert config.model == "provider-custom-model"
        assert config.messages_endpoint == "https://provider.example/custom/messages"
        assert config.base_url is None
        assert fake_anthropic.last_init_kwargs is None

    def test_custom_messages_endpoint_requires_credentials(self, monkeypatch):
        monkeypatch.setenv("ENTITY_LLM_MESSAGES_ENDPOINT", "https://provider.example/custom/messages")

        with pytest.raises(ClaudeConfigurationError, match="requires ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN"):
            ClaudeClient.resolve_config()

    def test_custom_messages_endpoint_requires_model_for_supplier_token(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "supplier-token")
        monkeypatch.setenv("ENTITY_LLM_MESSAGES_ENDPOINT", "https://provider.example/custom/messages")

        with pytest.raises(ClaudeConfigurationError, match="ENTITY_LLM_MODEL"):
            ClaudeClient.resolve_config()


class TestClaudeClientCustomEndpoint:
    def test_custom_endpoint_uses_bearer_auth_and_standard_payload(
        self,
        monkeypatch,
        fake_anthropic,
        fake_http_client,
    ):
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "supplier-token")
        monkeypatch.setenv("ENTITY_LLM_MODEL", "provider-custom-model")
        monkeypatch.setenv("ENTITY_LLM_MESSAGES_ENDPOINT", "https://provider.example/custom/messages")

        client = ClaudeClient()
        text = client.complete(
            system="You are concise.",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=42,
        )

        assert text == "endpoint response"
        assert fake_anthropic.last_init_kwargs is None
        assert fake_http_client.calls == [{
            "url": "https://provider.example/custom/messages",
            "headers": {
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
                "Authorization": "Bearer supplier-token",
            },
            "json": {
                "model": "provider-custom-model",
                "max_tokens": 42,
                "system": "You are concise.",
                "messages": [{"role": "user", "content": "hi"}],
            },
        }]

    def test_custom_endpoint_supports_openai_style_choice_response(
        self,
        monkeypatch,
        fake_http_client,
    ):
        fake_http_client.response = _FakeHTTPResponse(
            payload={"choices": [{"message": {"content": "choice response"}}]}
        )
        monkeypatch.setenv("ANTHROPIC_API_KEY", "official-key")
        monkeypatch.setenv("ENTITY_LLM_MESSAGES_ENDPOINT", "https://provider.example/custom/messages")

        client = ClaudeClient()
        text = client.complete(
            system="You are concise.",
            messages=[{"role": "user", "content": "hi"}],
        )

        assert text == "choice response"
        assert fake_http_client.calls[0]["headers"]["X-Api-Key"] == "official-key"

    def test_custom_endpoint_falls_back_to_plain_text_body(
        self,
        monkeypatch,
        fake_http_client,
    ):
        response = _FakeHTTPResponse(payload=None, text="plain text response")
        response.headers = {"content-type": "text/plain"}
        fake_http_client.response = response
        monkeypatch.setenv("ANTHROPIC_API_KEY", "official-key")
        monkeypatch.setenv("ENTITY_LLM_MESSAGES_ENDPOINT", "https://provider.example/custom/messages")

        client = ClaudeClient()
        text = client.complete(
            system="You are concise.",
            messages=[{"role": "user", "content": "hi"}],
        )

        assert text == "plain text response"
