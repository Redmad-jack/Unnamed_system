from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


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
        model: str = "claude-sonnet-4-6",
        api_key: Optional[str] = None,
    ) -> None:
        self._model = model
        # Import deferred to keep startup fast when running tests without API key.
        from anthropic import Anthropic
        self._client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

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
