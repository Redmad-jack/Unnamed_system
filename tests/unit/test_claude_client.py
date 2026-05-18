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


class _FakeStream:
    def __init__(self, chunks, final_message=None):
        self.text_stream = chunks
        self._final_message = final_message

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get_final_message(self):
        return self._final_message


class _FakeAnthropic:
    last_init_kwargs: dict | None = None
    last_stream_kwargs: dict | None = None
    response = None
    stream_response = None
    stream_error: Exception | None = None

    def __init__(self, **kwargs):
        type(self).last_init_kwargs = kwargs
        self.messages = types.SimpleNamespace(
            create=lambda **_: type(self).response,
            stream=self._stream,
        )

    def _stream(self, **kwargs):
        type(self).last_stream_kwargs = kwargs
        if type(self).stream_error is not None:
            raise type(self).stream_error
        return type(self).stream_response


@pytest.fixture(autouse=True)
def clear_llm_env(monkeypatch):
    for key in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ENTITY_LLM_MODEL",
        "ENTITY_LLM_MESSAGES_ENDPOINT",
        "ENTITY_LLM_DISABLE_SYSTEM_PROXY",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def fake_anthropic(monkeypatch):
    module = types.ModuleType("anthropic")
    module.Anthropic = _FakeAnthropic
    _FakeAnthropic.last_init_kwargs = None
    _FakeAnthropic.last_stream_kwargs = None
    _FakeAnthropic.response = types.SimpleNamespace(
        content=[types.SimpleNamespace(text="mock response")],
        stop_reason="end_turn",
        usage=types.SimpleNamespace(input_tokens=11, output_tokens=7),
    )
    _FakeAnthropic.stream_response = _FakeStream(
        ["mock ", "stream"],
        types.SimpleNamespace(
            content=[types.SimpleNamespace(text="mock stream")],
            stop_reason="end_turn",
            usage=types.SimpleNamespace(input_tokens=5, output_tokens=3),
        ),
    )
    _FakeAnthropic.stream_error = None
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


class _FakeHTTPStreamResponse:
    def __init__(self, lines, status_code: int = 200):
        self._lines = lines
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_lines(self):
        yield from self._lines

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeHTTPClient:
    calls: list[dict] = []
    response: _FakeHTTPResponse | None = None
    stream_response: _FakeHTTPStreamResponse | None = None
    stream_error: Exception | None = None
    init_kwargs: list[dict] = []

    def __init__(self, *args, **kwargs):
        type(self).calls = []
        type(self).init_kwargs.append(kwargs)

    def post(self, url, headers=None, json=None):
        type(self).calls.append({"url": url, "headers": headers or {}, "json": json or {}})
        assert type(self).response is not None
        return type(self).response

    def stream(self, method, url, headers=None, json=None):
        type(self).calls.append({
            "method": method,
            "url": url,
            "headers": headers or {},
            "json": json or {},
        })
        if type(self).stream_error is not None:
            raise type(self).stream_error
        assert type(self).stream_response is not None
        return type(self).stream_response


@pytest.fixture
def fake_http_client(monkeypatch):
    from conscious_entity.llm import claude_client as module

    _FakeHTTPClient.calls = []
    _FakeHTTPClient.init_kwargs = []
    _FakeHTTPClient.stream_response = None
    _FakeHTTPClient.stream_error = None
    _FakeHTTPClient.response = _FakeHTTPResponse(
        payload={"content": [{"type": "text", "text": "endpoint response"}]}
    )
    monkeypatch.setattr(module.httpx, "Client", _FakeHTTPClient)
    return _FakeHTTPClient


class TestClaudeClientConfig:
    def test_supplier_mode_uses_auth_token_and_base_url(
        self,
        monkeypatch,
        fake_anthropic,
        fake_http_client,
    ):
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "supplier-token")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://provider.example/anthropic")
        monkeypatch.setenv("ENTITY_LLM_MODEL", "provider-custom-model")

        client = ClaudeClient()

        assert client._model == "provider-custom-model"
        assert fake_anthropic.last_init_kwargs["api_key"] is None
        assert fake_anthropic.last_init_kwargs["auth_token"] == "supplier-token"
        assert fake_anthropic.last_init_kwargs["base_url"] == "https://provider.example/anthropic"
        assert isinstance(fake_anthropic.last_init_kwargs["http_client"], _FakeHTTPClient)
        assert fake_http_client.init_kwargs[0]["trust_env"] is True

    def test_official_mode_uses_api_key_and_default_model(
        self,
        monkeypatch,
        fake_anthropic,
        fake_http_client,
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "official-key")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy.example/anthropic")

        client = ClaudeClient()

        assert client._model == "claude-sonnet-4-6"
        assert fake_anthropic.last_init_kwargs["api_key"] == "official-key"
        assert fake_anthropic.last_init_kwargs["auth_token"] is None
        assert fake_anthropic.last_init_kwargs["base_url"] == "https://proxy.example/anthropic"
        assert isinstance(fake_anthropic.last_init_kwargs["http_client"], _FakeHTTPClient)
        assert fake_http_client.init_kwargs[0]["trust_env"] is True

    def test_explicit_model_overrides_environment_model(
        self,
        monkeypatch,
        fake_anthropic,
        fake_http_client,
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "official-key")
        monkeypatch.setenv("ENTITY_LLM_MODEL", "env-model")

        client = ClaudeClient(model="explicit-model")

        assert client._model == "explicit-model"
        assert fake_anthropic.last_init_kwargs["api_key"] == "official-key"
        assert fake_anthropic.last_init_kwargs["auth_token"] is None
        assert fake_anthropic.last_init_kwargs["base_url"] is None
        assert isinstance(fake_anthropic.last_init_kwargs["http_client"], _FakeHTTPClient)

    def test_disable_system_proxy_sets_trust_env_false(
        self,
        monkeypatch,
        fake_anthropic,
        fake_http_client,
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "official-key")
        monkeypatch.setenv("ENTITY_LLM_DISABLE_SYSTEM_PROXY", "1")

        ClaudeClient()

        assert fake_http_client.init_kwargs[0]["trust_env"] is False

    def test_runtime_config_can_ignore_environment_supplier_credentials(
        self,
        monkeypatch,
        fake_anthropic,
        fake_http_client,
    ):
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "supplier-token")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://provider.example/anthropic")
        monkeypatch.setenv("ENTITY_LLM_MODEL", "provider-custom-model")

        client = ClaudeClient(
            model="runtime-model",
            api_key="runtime-official-key",
            disable_system_proxy=True,
            use_env=False,
        )

        assert client._model == "runtime-model"
        assert fake_anthropic.last_init_kwargs["api_key"] == "runtime-official-key"
        assert fake_anthropic.last_init_kwargs["auth_token"] is None
        assert fake_anthropic.last_init_kwargs["base_url"] is None
        assert fake_http_client.init_kwargs[0]["trust_env"] is False

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
        assert fake_http_client.init_kwargs[0]["trust_env"] is True

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

    def test_custom_endpoint_can_disable_system_proxy(
        self,
        monkeypatch,
        fake_http_client,
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "official-key")
        monkeypatch.setenv("ENTITY_LLM_MESSAGES_ENDPOINT", "https://provider.example/custom/messages")
        monkeypatch.setenv("ENTITY_LLM_DISABLE_SYSTEM_PROXY", "true")

        ClaudeClient()

        assert fake_http_client.init_kwargs[0]["trust_env"] is False

    def test_complete_with_metadata_exposes_sdk_stop_reason_and_usage(
        self,
        monkeypatch,
        fake_anthropic,
        fake_http_client,
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "official-key")
        fake_anthropic.response = types.SimpleNamespace(
            content=[
                types.SimpleNamespace(text="part one"),
                types.SimpleNamespace(text=" + part two"),
            ],
            stop_reason="max_tokens",
            usage=types.SimpleNamespace(input_tokens=21, output_tokens=34),
        )

        client = ClaudeClient()
        completion = client.complete_with_metadata(
            system="You are concise.",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=42,
        )

        assert completion.text == "part one + part two"
        assert completion.stop_reason == "max_tokens"
        assert completion.prompt_tokens == 21
        assert completion.completion_tokens == 34

    def test_complete_streaming_with_metadata_collects_sdk_text_deltas(
        self,
        monkeypatch,
        fake_anthropic,
        fake_http_client,
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "official-key")
        fake_anthropic.stream_response = _FakeStream(
            ["part one", " + part two"],
            types.SimpleNamespace(
                content=[types.SimpleNamespace(text="part one + part two")],
                stop_reason="end_turn",
                usage=types.SimpleNamespace(input_tokens=31, output_tokens=17),
            ),
        )
        deltas = []

        client = ClaudeClient()
        completion = client.complete_streaming_with_metadata(
            system="You are concise.",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=42,
            on_text_delta=deltas.append,
        )

        assert completion.text == "part one + part two"
        assert completion.stop_reason == "end_turn"
        assert completion.prompt_tokens == 31
        assert completion.completion_tokens == 17
        assert deltas == ["part one", " + part two"]
        assert fake_anthropic.last_stream_kwargs == {
            "model": "claude-sonnet-4-6",
            "max_tokens": 42,
            "system": "You are concise.",
            "messages": [{"role": "user", "content": "hi"}],
        }

    def test_complete_streaming_callback_failure_does_not_abort(
        self,
        monkeypatch,
        fake_anthropic,
        fake_http_client,
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "official-key")
        fake_anthropic.stream_response = _FakeStream(
            ["safe"],
            types.SimpleNamespace(
                content=[types.SimpleNamespace(text="safe")],
                stop_reason="end_turn",
                usage=types.SimpleNamespace(input_tokens=1, output_tokens=1),
            ),
        )

        def bad_callback(_delta):
            raise RuntimeError("callback failed")

        client = ClaudeClient()
        completion = client.complete_streaming_with_metadata(
            system="You are concise.",
            messages=[{"role": "user", "content": "hi"}],
            on_text_delta=bad_callback,
        )

        assert completion.text == "safe"
        assert completion.stop_reason == "end_turn"

    def test_complete_streaming_keeps_collected_text_when_final_message_unavailable(
        self,
        monkeypatch,
        fake_anthropic,
        fake_http_client,
    ):
        class _BrokenFinalStream(_FakeStream):
            def get_final_message(self):
                raise RuntimeError("missing final message")

        monkeypatch.setenv("ANTHROPIC_API_KEY", "official-key")
        fake_anthropic.stream_response = _BrokenFinalStream(["collected"])

        client = ClaudeClient()
        completion = client.complete_streaming_with_metadata(
            system="You are concise.",
            messages=[{"role": "user", "content": "hi"}],
        )

        assert completion.text == "collected"
        assert completion.stop_reason is None
        assert completion.prompt_tokens == 0
        assert completion.completion_tokens == 0

    def test_complete_streaming_falls_back_for_custom_endpoint(
        self,
        monkeypatch,
        fake_http_client,
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "official-key")
        monkeypatch.setenv("ENTITY_LLM_MESSAGES_ENDPOINT", "https://provider.example/custom/messages")

        client = ClaudeClient()
        completion = client.complete_streaming_with_metadata(
            system="You are concise.",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=42,
        )

        assert completion.text == "endpoint response"
        assert fake_http_client.calls[0]["url"] == "https://provider.example/custom/messages"

    def test_complete_streaming_custom_endpoint_reads_sse_deltas(
        self,
        monkeypatch,
        fake_http_client,
    ):
        fake_http_client.stream_response = _FakeHTTPStreamResponse([
            "event: content_block_delta",
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"first "}}',
            "",
            "event: content_block_delta",
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"second"}}',
            "",
            'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":9}}',
            "",
            "data: [DONE]",
            "",
        ])
        monkeypatch.setenv("ANTHROPIC_API_KEY", "official-key")
        monkeypatch.setenv("ENTITY_LLM_MESSAGES_ENDPOINT", "https://provider.example/custom/messages")
        deltas = []

        client = ClaudeClient()
        completion = client.complete_streaming_with_metadata(
            system="You are concise.",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=42,
            on_text_delta=deltas.append,
        )

        assert completion.text == "first second"
        assert completion.stop_reason == "end_turn"
        assert completion.completion_tokens == 9
        assert deltas == ["first ", "second"]
        assert fake_http_client.calls[0]["method"] == "POST"
        assert fake_http_client.calls[0]["url"] == "https://provider.example/custom/messages"
        assert fake_http_client.calls[0]["json"]["stream"] is True
        assert fake_http_client.calls[0]["headers"]["accept"] == "text/event-stream"

    def test_complete_streaming_sdk_error_uses_raw_base_url_sse_before_fallback(
        self,
        monkeypatch,
        fake_anthropic,
        fake_http_client,
    ):
        fake_anthropic.stream_error = RuntimeError("sdk stream unavailable")
        fake_http_client.stream_response = _FakeHTTPStreamResponse([
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"raw stream"}}',
            "",
            "data: [DONE]",
            "",
        ])
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "supplier-token")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://provider.example")
        monkeypatch.setenv("ENTITY_LLM_MODEL", "provider-custom-model")

        client = ClaudeClient()
        completion = client.complete_streaming_with_metadata(
            system="You are concise.",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=42,
        )

        assert completion.text == "raw stream"
        assert fake_http_client.calls[0]["url"] == "https://provider.example/v1/messages"
        assert fake_http_client.calls[0]["headers"]["Authorization"] == "Bearer supplier-token"

    def test_complete_streaming_sdk_error_falls_back_to_non_streaming(
        self,
        monkeypatch,
        fake_anthropic,
        fake_http_client,
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "official-key")
        fake_anthropic.stream_error = RuntimeError("stream unavailable")
        fake_anthropic.response = types.SimpleNamespace(
            content=[types.SimpleNamespace(text="fallback response")],
            stop_reason="end_turn",
            usage=types.SimpleNamespace(input_tokens=8, output_tokens=5),
        )

        client = ClaudeClient()
        completion = client.complete_streaming_with_metadata(
            system="You are concise.",
            messages=[{"role": "user", "content": "hi"}],
        )

        assert completion.text == "fallback response"
        assert completion.prompt_tokens == 8
        assert completion.completion_tokens == 5

    def test_complete_with_metadata_exposes_custom_endpoint_stop_reason(
        self,
        monkeypatch,
        fake_http_client,
    ):
        fake_http_client.response = _FakeHTTPResponse(
            payload={
                "content": [{"type": "text", "text": "partial response"}],
                "stop_reason": "max_tokens",
                "usage": {"input_tokens": 13, "output_tokens": 29},
            }
        )
        monkeypatch.setenv("ANTHROPIC_API_KEY", "official-key")
        monkeypatch.setenv("ENTITY_LLM_MESSAGES_ENDPOINT", "https://provider.example/custom/messages")

        client = ClaudeClient()
        completion = client.complete_with_metadata(
            system="You are concise.",
            messages=[{"role": "user", "content": "hi"}],
        )

        assert completion.text == "partial response"
        assert completion.stop_reason == "max_tokens"
        assert completion.prompt_tokens == 13
        assert completion.completion_tokens == 29
