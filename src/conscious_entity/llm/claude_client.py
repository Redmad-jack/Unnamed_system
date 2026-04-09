from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

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
    ) -> None:
        config = self.resolve_config(
            model=model,
            api_key=api_key,
            auth_token=auth_token,
            base_url=base_url,
            messages_endpoint=messages_endpoint,
        )
        self._model = config.model
        self._messages_endpoint = config.messages_endpoint
        self._http_client: httpx.Client | None = None

        if self._messages_endpoint:
            self._client = None
            self._http_client = httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0))
        else:
            # Import deferred to keep startup fast when running tests without API key.
            from anthropic import Anthropic
            self._client = Anthropic(
                api_key=config.api_key,
                auth_token=config.auth_token,
                base_url=config.base_url,
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
    ) -> ClaudeClientConfig:
        resolved_model = model or os.environ.get("ENTITY_LLM_MODEL")
        resolved_api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        resolved_auth_token = auth_token or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        resolved_base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL")
        resolved_messages_endpoint = messages_endpoint or os.environ.get("ENTITY_LLM_MESSAGES_ENDPOINT")

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
                )

            if resolved_api_key:
                return ClaudeClientConfig(
                    model=resolved_model or _DEFAULT_MODEL,
                    api_key=resolved_api_key,
                    auth_token=None,
                    base_url=resolved_base_url,
                    messages_endpoint=resolved_messages_endpoint,
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
            )

        if resolved_api_key:
            return ClaudeClientConfig(
                model=resolved_model or _DEFAULT_MODEL,
                api_key=resolved_api_key,
                auth_token=None,
                base_url=resolved_base_url,
                messages_endpoint=None,
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
        try:
            if self._messages_endpoint:
                return self._complete_via_custom_endpoint(system, messages, max_tokens)

            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            return response.content[0].text
        except Exception as exc:
            logger.error(
                "LLM call failed (model=%s, max_tokens=%d): %s",
                self._model,
                max_tokens,
                exc,
            )
            return ""

    def _complete_via_custom_endpoint(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int,
    ) -> str:
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
        return self._extract_text_from_response(response)

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

    def _extract_text_from_response(self, response: httpx.Response) -> str:
        payload: object
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError):
            return response.text.strip()

        text = self._extract_text_from_payload(payload)
        if text is not None:
            return text

        return response.text.strip()

    @classmethod
    def _extract_text_from_payload(cls, payload: object) -> str | None:
        if isinstance(payload, dict):
            content = payload.get("content")
            if isinstance(content, list):
                texts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text")
                        if isinstance(text, str):
                            texts.append(text)
                if texts:
                    return "".join(texts)
            if isinstance(content, str):
                return content

            output_text = payload.get("output_text")
            if isinstance(output_text, str):
                return output_text

            choices = payload.get("choices")
            if isinstance(choices, list) and choices:
                first_choice = choices[0]
                if isinstance(first_choice, dict):
                    message = first_choice.get("message")
                    if isinstance(message, dict):
                        message_content = message.get("content")
                        text = cls._extract_choice_content_text(message_content)
                        if text is not None:
                            return text
                    text = first_choice.get("text")
                    if isinstance(text, str):
                        return text

        if isinstance(payload, str):
            return payload

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
