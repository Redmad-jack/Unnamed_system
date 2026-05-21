from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

import httpx

logger = logging.getLogger(__name__)


_DEFAULT_MODEL = "claude-sonnet-4-6"


class ClaudeConfigurationError(RuntimeError):
    """Raised when required LLM configuration is missing or inconsistent."""


@dataclass(frozen=True)
class ClaudeClientConfig:
    model: str
    api_key: str | None
    auth_token: str | None
    base_url: str | None
    messages_endpoint: str | None
    disable_system_proxy: bool


@dataclass(frozen=True)
class ClaudeCompletion:
    text: str
    stop_reason: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class ClaudeClient:
    """
    Thin wrapper around the Anthropic SDK.

    This is the ONLY place in the system that calls the Anthropic API.
    Both ExpressionEngine and ReflectionEngine (v0.2) use this class.

    To use a different model (e.g. Haiku for reflection):
        client = ClaudeClient(model="claude-haiku-4-5-20251001")

    To mock in tests:
        monkeypatch.setattr(ClaudeClient, "complete", lambda *a, **kw: "mock response")
    Or inject a mock instance directly into ExpressionEngine.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: Optional[str] = None,
        auth_token: Optional[str] = None,
        base_url: Optional[str] = None,
        messages_endpoint: Optional[str] = None,
        disable_system_proxy: bool | None = None,
        use_env: bool = True,
    ) -> None:
        config = self.resolve_config(
            model=model,
            api_key=api_key,
            auth_token=auth_token,
            base_url=base_url,
            messages_endpoint=messages_endpoint,
            disable_system_proxy=disable_system_proxy,
            use_env=use_env,
        )
        self._model = config.model
        self._base_url = config.base_url
        self._messages_endpoint = config.messages_endpoint
        http_client = self._build_http_client(config.disable_system_proxy)
        self._http_client: httpx.Client | None = http_client

        if self._messages_endpoint:
            self._client = None
        else:
            # Import deferred to keep startup fast when running tests without API key.
            from anthropic import Anthropic
            self._client = Anthropic(
                api_key=config.api_key,
                auth_token=config.auth_token,
                base_url=config.base_url,
                http_client=http_client,
            )
        self._api_key = config.api_key
        self._auth_token = config.auth_token

    @classmethod
    def resolve_config(
        cls,
        model: str | None = None,
        api_key: str | None = None,
        auth_token: str | None = None,
        base_url: str | None = None,
        messages_endpoint: str | None = None,
        disable_system_proxy: bool | None = None,
        use_env: bool = True,
    ) -> ClaudeClientConfig:
        resolved_model = model or (os.environ.get("ENTITY_LLM_MODEL") if use_env else None)
        resolved_api_key = api_key or (os.environ.get("ANTHROPIC_API_KEY") if use_env else None)
        resolved_auth_token = auth_token or (os.environ.get("ANTHROPIC_AUTH_TOKEN") if use_env else None)
        resolved_base_url = base_url or (os.environ.get("ANTHROPIC_BASE_URL") if use_env else None)
        resolved_messages_endpoint = messages_endpoint or (
            os.environ.get("ENTITY_LLM_MESSAGES_ENDPOINT") if use_env else None
        )
        resolved_disable_system_proxy = (
            disable_system_proxy
            if disable_system_proxy is not None
            else cls._env_flag("ENTITY_LLM_DISABLE_SYSTEM_PROXY")
        )

        if resolved_messages_endpoint:
            if resolved_auth_token:
                if not resolved_model:
                    raise ClaudeConfigurationError(
                        "Custom messages endpoint mode requires ENTITY_LLM_MODEL when using "
                        "ANTHROPIC_AUTH_TOKEN."
                    )
                return ClaudeClientConfig(
                    model=resolved_model,
                    api_key=None,
                    auth_token=resolved_auth_token,
                    base_url=resolved_base_url,
                    messages_endpoint=resolved_messages_endpoint,
                    disable_system_proxy=resolved_disable_system_proxy,
                )

            if resolved_api_key:
                return ClaudeClientConfig(
                    model=resolved_model or _DEFAULT_MODEL,
                    api_key=resolved_api_key,
                    auth_token=None,
                    base_url=resolved_base_url,
                    messages_endpoint=resolved_messages_endpoint,
                    disable_system_proxy=resolved_disable_system_proxy,
                )

            raise ClaudeConfigurationError(
                "Custom messages endpoint mode requires ANTHROPIC_API_KEY or "
                "ANTHROPIC_AUTH_TOKEN."
            )

        if resolved_auth_token:
            missing = []
            if not resolved_base_url:
                missing.append("ANTHROPIC_BASE_URL")
            if not resolved_model:
                missing.append("ENTITY_LLM_MODEL")
            if missing:
                raise ClaudeConfigurationError(
                    "Supplier mode is incomplete. Set ANTHROPIC_AUTH_TOKEN plus "
                    + ", ".join(missing)
                    + "."
                )
            return ClaudeClientConfig(
                model=resolved_model,
                api_key=None,
                auth_token=resolved_auth_token,
                base_url=resolved_base_url,
                messages_endpoint=None,
                disable_system_proxy=resolved_disable_system_proxy,
            )

        if resolved_api_key:
            return ClaudeClientConfig(
                model=resolved_model or _DEFAULT_MODEL,
                api_key=resolved_api_key,
                auth_token=None,
                base_url=resolved_base_url,
                messages_endpoint=None,
                disable_system_proxy=resolved_disable_system_proxy,
            )

        if resolved_base_url or resolved_model:
            raise ClaudeConfigurationError(
                "LLM credentials are incomplete. Use ANTHROPIC_API_KEY for official mode, "
                "or ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL + ENTITY_LLM_MODEL for supplier mode. "
                "For non-standard gateways, set ENTITY_LLM_MESSAGES_ENDPOINT."
            )

        raise ClaudeConfigurationError(
            "Missing LLM credentials. Set ANTHROPIC_API_KEY for official mode, or "
            "ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL + ENTITY_LLM_MODEL for supplier mode. "
            "For non-standard gateways, set ENTITY_LLM_MESSAGES_ENDPOINT."
        )

    @staticmethod
    def _env_flag(name: str) -> bool:
        value = os.environ.get(name)
        if value is None:
            return False
        return value.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _build_http_client(disable_system_proxy: bool) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(20.0, connect=5.0),
            trust_env=not disable_system_proxy,
        )

    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 300,
    ) -> str:
        """
        Call the Anthropic Messages API and return the generated text.

        Args:
            system:     System prompt string.
            messages:   List of {"role": "user"|"assistant", "content": str} dicts
                        in chronological order. Must start with a "user" message.
            max_tokens: Maximum tokens to generate.

        Returns:
            Generated text string, or "" on failure (caller handles fallback).
        """
        return self.complete_with_metadata(system, messages, max_tokens).text

    def complete_with_metadata(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 300,
    ) -> ClaudeCompletion:
        start = time.monotonic()
        completion = ClaudeCompletion(text="")
        error_msg: str | None = None

        try:
            if self._messages_endpoint:
                completion = self._complete_via_custom_endpoint(system, messages, max_tokens)
            else:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=messages,
                )
                completion = ClaudeCompletion(
                    text=self._collect_response_text(response.content),
                    stop_reason=getattr(response, "stop_reason", None),
                    prompt_tokens=(
                        getattr(response.usage, "input_tokens", 0) or 0
                        if hasattr(response, "usage") and response.usage
                        else 0
                    ),
                    completion_tokens=(
                        getattr(response.usage, "output_tokens", 0) or 0
                        if hasattr(response, "usage") and response.usage
                        else 0
                    ),
                )
        except Exception as exc:
            error_msg = str(exc)
            logger.error(
                "LLM call failed (model=%s, max_tokens=%d): %s",
                self._model,
                max_tokens,
                exc,
            )
        finally:
            self._record_completion_stats(start, completion, error_msg)

        return completion

    def complete_streaming_with_metadata(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 300,
        on_text_delta: Callable[[str], None] | None = None,
    ) -> ClaudeCompletion:
        """
        Stream Anthropic text deltas internally while preserving the old return shape.

        Public callers still receive one complete ClaudeCompletion. Custom endpoint
        mode and any SDK streaming failure fall back to complete_with_metadata().
        """
        if self._messages_endpoint:
            return self._complete_streaming_http_with_fallback(
                system,
                messages,
                max_tokens,
                on_text_delta=on_text_delta,
                endpoint=self._messages_endpoint,
            )
        if self._client is None:
            return self._with_streaming_diagnostics(
                self.complete_with_metadata(system, messages, max_tokens),
                used_sdk_stream=False,
                used_http_sse=False,
                fell_back_to_non_streaming=True,
                first_text_delta_ms=None,
                delta_count=0,
                thinking_delta_count=0,
            )

        messages_client = getattr(self._client, "messages", None)
        stream_factory = getattr(messages_client, "stream", None)
        if not callable(stream_factory):
            endpoint = self._derived_messages_endpoint()
            if endpoint is not None:
                return self._complete_streaming_http_with_fallback(
                    system,
                    messages,
                    max_tokens,
                    on_text_delta=on_text_delta,
                    endpoint=endpoint,
                )
            return self._with_streaming_diagnostics(
                self.complete_with_metadata(system, messages, max_tokens),
                used_sdk_stream=False,
                used_http_sse=False,
                fell_back_to_non_streaming=True,
                first_text_delta_ms=None,
                delta_count=0,
                thinking_delta_count=0,
            )

        start = time.monotonic()
        completion = ClaudeCompletion(text="")

        try:
            collected: list[str] = []
            final_message = None
            first_text_delta_ms: int | None = None
            delta_count = 0
            with stream_factory(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            ) as stream:
                text_stream = getattr(stream, "text_stream", None)
                if text_stream is None:
                    raise RuntimeError("Anthropic streaming response did not expose text_stream.")
                for delta in text_stream:
                    if delta is None:
                        continue
                    text_delta = delta if isinstance(delta, str) else str(delta)
                    if not text_delta:
                        continue
                    delta_count += 1
                    if first_text_delta_ms is None:
                        first_text_delta_ms = int((time.monotonic() - start) * 1000)
                    collected.append(text_delta)
                    if on_text_delta is not None:
                        try:
                            on_text_delta(text_delta)
                        except Exception as exc:
                            logger.warning("LLM streaming text delta callback failed: %s", exc)

                get_final_message = getattr(stream, "get_final_message", None)
                if callable(get_final_message):
                    try:
                        final_message = get_final_message()
                    except Exception as exc:
                        logger.warning("LLM streaming final message was unavailable: %s", exc)

            text = "".join(collected)
            if not text and final_message is not None:
                text = self._collect_response_text(getattr(final_message, "content", None))
            prompt_tokens, completion_tokens = self._extract_usage(
                getattr(final_message, "usage", None) if final_message is not None else None
            )
            completion = ClaudeCompletion(
                text=text,
                stop_reason=(
                    getattr(final_message, "stop_reason", None)
                    if final_message is not None
                    else None
                ),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                metadata=self._streaming_diagnostics(
                    used_sdk_stream=True,
                    used_http_sse=False,
                    fell_back_to_non_streaming=False,
                    first_text_delta_ms=first_text_delta_ms,
                    delta_count=delta_count,
                    thinking_delta_count=0,
                ),
            )
        except Exception as exc:
            logger.warning(
                "LLM streaming call failed (model=%s, max_tokens=%d); falling back: %s",
                self._model,
                max_tokens,
                exc,
            )
            endpoint = self._derived_messages_endpoint()
            if endpoint is not None:
                return self._complete_streaming_http_with_fallback(
                    system,
                    messages,
                    max_tokens,
                    on_text_delta=on_text_delta,
                    endpoint=endpoint,
                )
            return self._with_streaming_diagnostics(
                self.complete_with_metadata(system, messages, max_tokens),
                used_sdk_stream=False,
                used_http_sse=False,
                fell_back_to_non_streaming=True,
                first_text_delta_ms=None,
                delta_count=0,
                thinking_delta_count=0,
            )

        self._record_completion_stats(start, completion, None)
        return completion

    def _complete_streaming_http_with_fallback(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int,
        *,
        on_text_delta: Callable[[str], None] | None,
        endpoint: str,
    ) -> ClaudeCompletion:
        start = time.monotonic()
        completion = ClaudeCompletion(text="")
        try:
            completion = self._complete_via_streaming_http_endpoint(
                system,
                messages,
                max_tokens,
                on_text_delta=on_text_delta,
                endpoint=endpoint,
            )
        except Exception as exc:
            logger.warning(
                "LLM HTTP streaming call failed (endpoint=%s, model=%s, max_tokens=%d); falling back: %s",
                endpoint,
                self._model,
                max_tokens,
                exc,
            )
            return self._with_streaming_diagnostics(
                self.complete_with_metadata(system, messages, max_tokens),
                used_sdk_stream=False,
                used_http_sse=False,
                fell_back_to_non_streaming=True,
                first_text_delta_ms=None,
                delta_count=0,
                thinking_delta_count=0,
            )
        self._record_completion_stats(start, completion, None)
        return completion

    def _complete_via_streaming_http_endpoint(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int,
        *,
        on_text_delta: Callable[[str], None] | None,
        endpoint: str,
    ) -> ClaudeCompletion:
        if self._http_client is None:
            raise RuntimeError("HTTP client is not initialized.")

        collected: list[str] = []
        stop_reason: str | None = None
        prompt_tokens = 0
        completion_tokens = 0
        final_payload: object | None = None
        start = time.monotonic()
        first_text_delta_ms: int | None = None
        delta_count = 0
        thinking_delta_count = 0

        with self._http_client.stream(
            "POST",
            endpoint,
            headers={**self._custom_endpoint_headers(), "accept": "text/event-stream"},
            json={
                "model": self._model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": messages,
                "stream": True,
            },
        ) as response:
            response.raise_for_status()
            for payload in self._iter_sse_payloads(response):
                if payload == "[DONE]":
                    break
                try:
                    event = json.loads(payload)
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                final_payload = event
                event_stop_reason = self._stream_stop_reason(event)
                if event_stop_reason:
                    stop_reason = event_stop_reason
                if self._stream_is_thinking_delta(event):
                    thinking_delta_count += 1
                usage_prompt, usage_completion = self._stream_usage(event)
                prompt_tokens = usage_prompt or prompt_tokens
                completion_tokens = usage_completion or completion_tokens
                text_delta = self._stream_text_delta(event)
                if not text_delta:
                    continue
                delta_count += 1
                if first_text_delta_ms is None:
                    first_text_delta_ms = int((time.monotonic() - start) * 1000)
                collected.append(text_delta)
                if on_text_delta is not None:
                    try:
                        on_text_delta(text_delta)
                    except Exception as exc:
                        logger.warning("LLM HTTP streaming text delta callback failed: %s", exc)

        text = "".join(collected)
        if not text and final_payload is not None:
            fallback = self._extract_completion_from_payload(final_payload)
            if fallback is not None:
                text = fallback.text
                stop_reason = stop_reason or fallback.stop_reason
                prompt_tokens = prompt_tokens or fallback.prompt_tokens
                completion_tokens = completion_tokens or fallback.completion_tokens

        return ClaudeCompletion(
            text=text,
            stop_reason=stop_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            metadata=self._streaming_diagnostics(
                used_sdk_stream=False,
                used_http_sse=True,
                fell_back_to_non_streaming=False,
                first_text_delta_ms=first_text_delta_ms,
                delta_count=delta_count,
                thinking_delta_count=thinking_delta_count,
            ),
        )

    @staticmethod
    def _streaming_diagnostics(
        *,
        used_sdk_stream: bool,
        used_http_sse: bool,
        fell_back_to_non_streaming: bool,
        first_text_delta_ms: int | None,
        delta_count: int,
        thinking_delta_count: int,
    ) -> dict[str, Any]:
        return {
            "used_sdk_stream": used_sdk_stream,
            "used_http_sse": used_http_sse,
            "fell_back_to_non_streaming": fell_back_to_non_streaming,
            "first_text_delta_ms": first_text_delta_ms,
            "delta_count": delta_count,
            "thinking_delta_count": thinking_delta_count,
        }

    @classmethod
    def _with_streaming_diagnostics(
        cls,
        completion: ClaudeCompletion,
        *,
        used_sdk_stream: bool,
        used_http_sse: bool,
        fell_back_to_non_streaming: bool,
        first_text_delta_ms: int | None,
        delta_count: int,
        thinking_delta_count: int,
    ) -> ClaudeCompletion:
        return ClaudeCompletion(
            text=completion.text,
            stop_reason=completion.stop_reason,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
            metadata={
                **completion.metadata,
                **cls._streaming_diagnostics(
                    used_sdk_stream=used_sdk_stream,
                    used_http_sse=used_http_sse,
                    fell_back_to_non_streaming=fell_back_to_non_streaming,
                    first_text_delta_ms=first_text_delta_ms,
                    delta_count=delta_count,
                    thinking_delta_count=thinking_delta_count,
                ),
            },
        )

    def _derived_messages_endpoint(self) -> str | None:
        if not self._base_url:
            return None
        base = self._base_url.rstrip("/")
        if base.endswith("/v1"):
            return f"{base}/messages"
        return f"{base}/v1/messages"

    @staticmethod
    def _iter_sse_payloads(response: object):
        data_lines: list[str] = []
        for raw_line in response.iter_lines():
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else str(raw_line)
            line = line.rstrip("\r")
            if not line:
                if data_lines:
                    yield "\n".join(data_lines)
                    data_lines = []
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if data_lines:
            yield "\n".join(data_lines)

    @classmethod
    def _stream_text_delta(cls, payload: object) -> str:
        if not isinstance(payload, dict):
            return ""
        event_type = payload.get("type")
        if event_type == "content_block_delta":
            delta = payload.get("delta")
            if isinstance(delta, dict):
                text = delta.get("text")
                if isinstance(text, str):
                    return text
        if event_type == "text_delta":
            text = payload.get("text")
            if isinstance(text, str):
                return text
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                delta = first.get("delta")
                if isinstance(delta, dict):
                    content = delta.get("content")
                    if isinstance(content, str):
                        return content
                    if isinstance(content, list):
                        return "".join(
                            item.get("text", "")
                            for item in content
                            if isinstance(item, dict) and isinstance(item.get("text"), str)
                        )
                text = first.get("text")
                if isinstance(text, str):
                    return text
        return ""

    @classmethod
    def _stream_is_thinking_delta(cls, payload: object) -> bool:
        if not isinstance(payload, dict):
            return False
        event_type = payload.get("type")
        if event_type == "thinking_delta":
            return True
        if event_type == "content_block_delta":
            delta = payload.get("delta")
            return isinstance(delta, dict) and delta.get("type") == "thinking_delta"
        return False

    @classmethod
    def _stream_stop_reason(cls, payload: object) -> str | None:
        if not isinstance(payload, dict):
            return None
        direct = cls._first_string(payload.get("stop_reason"), payload.get("finish_reason"))
        if direct:
            return direct
        delta = payload.get("delta")
        if isinstance(delta, dict):
            value = cls._first_string(delta.get("stop_reason"), delta.get("finish_reason"))
            if value:
                return value
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                return cls._first_string(first.get("finish_reason"), first.get("stop_reason"))
        return None

    @classmethod
    def _stream_usage(cls, payload: object) -> tuple[int, int]:
        if not isinstance(payload, dict):
            return 0, 0
        prompt_tokens, completion_tokens = cls._extract_usage(payload.get("usage"))
        message = payload.get("message")
        if isinstance(message, dict):
            msg_prompt, msg_completion = cls._extract_usage(message.get("usage"))
            prompt_tokens = prompt_tokens or msg_prompt
            completion_tokens = completion_tokens or msg_completion
        return prompt_tokens, completion_tokens

    def _complete_via_custom_endpoint(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int,
    ) -> ClaudeCompletion:
        if self._http_client is None or self._messages_endpoint is None:
            raise RuntimeError("Custom endpoint client is not initialized.")

        response = self._http_client.post(
            self._messages_endpoint,
            headers=self._custom_endpoint_headers(),
            json={
                "model": self._model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": messages,
            },
        )
        response.raise_for_status()
        return self._extract_completion_from_response(response)

    def _custom_endpoint_headers(self) -> dict[str, str]:
        headers = {
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        if self._api_key:
            headers["X-Api-Key"] = self._api_key
        return headers

    def _extract_completion_from_response(self, response: httpx.Response) -> ClaudeCompletion:
        payload: object
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError):
            return ClaudeCompletion(text=response.text.strip())

        completion = self._extract_completion_from_payload(payload)
        if completion is not None:
            return completion

        return ClaudeCompletion(text=response.text.strip())

    @classmethod
    def _extract_completion_from_payload(cls, payload: object) -> ClaudeCompletion | None:
        if isinstance(payload, dict):
            stop_reason = cls._first_string(
                payload.get("stop_reason"),
                payload.get("finish_reason"),
            )
            prompt_tokens, completion_tokens = cls._extract_usage(payload.get("usage"))

            content = payload.get("content")
            if isinstance(content, list):
                texts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text")
                        if isinstance(text, str):
                            texts.append(text)
                if texts:
                    return ClaudeCompletion(
                        text="".join(texts),
                        stop_reason=stop_reason,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                    )
            if isinstance(content, str):
                return ClaudeCompletion(
                    text=content,
                    stop_reason=stop_reason,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )

            output_text = payload.get("output_text")
            if isinstance(output_text, str):
                return ClaudeCompletion(
                    text=output_text,
                    stop_reason=stop_reason,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )

            choices = payload.get("choices")
            if isinstance(choices, list) and choices:
                first_choice = choices[0]
                if isinstance(first_choice, dict):
                    choice_stop_reason = cls._first_string(
                        first_choice.get("finish_reason"),
                        stop_reason,
                    )
                    message = first_choice.get("message")
                    if isinstance(message, dict):
                        message_content = message.get("content")
                        text = cls._extract_choice_content_text(message_content)
                        if text is not None:
                            return ClaudeCompletion(
                                text=text,
                                stop_reason=choice_stop_reason,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                            )
                    text = first_choice.get("text")
                    if isinstance(text, str):
                        return ClaudeCompletion(
                            text=text,
                            stop_reason=choice_stop_reason,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                        )

        if isinstance(payload, str):
            return ClaudeCompletion(text=payload)

        return None

    @classmethod
    def _extract_choice_content_text(cls, content: object) -> str | None:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        texts.append(text)
            if texts:
                return "".join(texts)
        return None

    @staticmethod
    def _collect_response_text(content: object) -> str:
        if isinstance(content, list):
            texts = []
            for block in content:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    texts.append(text)
            if texts:
                return "".join(texts)
        return ""

    @staticmethod
    def _extract_usage(usage: object) -> tuple[int, int]:
        if isinstance(usage, dict):
            prompt_tokens = usage.get("input_tokens")
            if prompt_tokens is None:
                prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("output_tokens")
            if completion_tokens is None:
                completion_tokens = usage.get("completion_tokens")
            return int(prompt_tokens or 0), int(completion_tokens or 0)
        if usage is not None:
            prompt_tokens = getattr(usage, "input_tokens", None)
            if prompt_tokens is None:
                prompt_tokens = getattr(usage, "prompt_tokens", None)
            completion_tokens = getattr(usage, "output_tokens", None)
            if completion_tokens is None:
                completion_tokens = getattr(usage, "completion_tokens", None)
            return int(prompt_tokens or 0), int(completion_tokens or 0)
        return 0, 0

    @staticmethod
    def _first_string(*values: object) -> str | None:
        for value in values:
            if isinstance(value, str) and value:
                return value
        return None

    def _record_completion_stats(
        self,
        start: float,
        completion: ClaudeCompletion,
        error_msg: str | None,
    ) -> None:
        from conscious_entity.llm.stats_tracker import LLMCallRecord, get_tracker

        duration_ms = int((time.monotonic() - start) * 1000)
        try:
            get_tracker().record(
                LLMCallRecord(
                    timestamp=datetime.now(),
                    model=self._model,
                    duration_ms=duration_ms,
                    success=bool(completion.text),
                    error=error_msg,
                    prompt_tokens=completion.prompt_tokens,
                    completion_tokens=completion.completion_tokens,
                )
            )
        except Exception:
            pass  # stats recording is optional; never break the call path
