from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class EmbeddingConfigurationError(RuntimeError):
    """Raised when embedding retrieval is enabled but configuration is incomplete."""


class EmbeddingRequestError(RuntimeError):
    """Raised when the embedding provider call fails or returns an invalid body."""


@dataclass(frozen=True)
class EmbeddingClientConfig:
    mode: str
    model: str | None
    api_key: str | None
    base_url: str | None
    endpoint: str | None


class EmbeddingClient:
    """
    Minimal OpenAI-compatible embedding client.

    The system treats embeddings as an optional retrieval enhancement. If the
    client is disabled or a call fails, callers should fall back to deterministic
    retrieval rather than interrupting the dialog.
    """

    def __init__(
        self,
        mode: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        endpoint: str | None = None,
        timeout: float = 20.0,
        use_env: bool = True,
    ) -> None:
        self._config = self.resolve_config(
            mode=mode,
            model=model,
            api_key=api_key,
            base_url=base_url,
            endpoint=endpoint,
            use_env=use_env,
        )
        self._timeout = timeout

    @classmethod
    def from_env(cls) -> EmbeddingClient:
        return cls()

    @classmethod
    def resolve_config(
        cls,
        mode: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        endpoint: str | None = None,
        use_env: bool = True,
    ) -> EmbeddingClientConfig:
        resolved_mode = (mode or (os.getenv("ENTITY_EMBEDDING_MODE") if use_env else None) or "disabled").strip()
        resolved_model = model or (os.getenv("ENTITY_EMBEDDING_MODEL") if use_env else None)
        resolved_api_key = api_key or (os.getenv("ENTITY_EMBEDDING_API_KEY") if use_env else None)
        resolved_base_url = base_url or (os.getenv("ENTITY_EMBEDDING_BASE_URL") if use_env else None)
        resolved_endpoint = endpoint or (os.getenv("ENTITY_EMBEDDING_ENDPOINT") if use_env else None)

        if resolved_mode not in {"disabled", "openai_compatible"}:
            raise EmbeddingConfigurationError(
                "ENTITY_EMBEDDING_MODE must be disabled or openai_compatible."
            )
        if resolved_mode == "openai_compatible":
            missing = []
            if not resolved_model:
                missing.append("ENTITY_EMBEDDING_MODEL")
            if not resolved_api_key:
                missing.append("ENTITY_EMBEDDING_API_KEY")
            if not resolved_endpoint and not resolved_base_url:
                missing.append("ENTITY_EMBEDDING_ENDPOINT or ENTITY_EMBEDDING_BASE_URL")
            if missing:
                raise EmbeddingConfigurationError(
                    "Embedding mode is incomplete. Set " + ", ".join(missing) + "."
                )

        return EmbeddingClientConfig(
            mode=resolved_mode,
            model=resolved_model,
            api_key=resolved_api_key,
            base_url=resolved_base_url,
            endpoint=resolved_endpoint,
        )

    @property
    def enabled(self) -> bool:
        return self._config.mode == "openai_compatible"

    @property
    def model(self) -> str | None:
        return self._config.model

    def embed(self, text: str) -> list[float]:
        if not self.enabled:
            raise EmbeddingConfigurationError("Embedding client is disabled.")
        if not text.strip():
            raise EmbeddingRequestError("Cannot embed empty text.")

        endpoint = self._endpoint()
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._config.model,
            "input": text,
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise EmbeddingRequestError(str(exc)) from exc

        embedding = _extract_embedding(data)
        if not embedding:
            raise EmbeddingRequestError("Embedding response did not contain a vector.")
        return embedding

    def _endpoint(self) -> str:
        if self._config.endpoint:
            return self._config.endpoint
        assert self._config.base_url is not None
        return self._config.base_url.rstrip("/") + "/embeddings"


def _extract_embedding(data: Any) -> list[float]:
    if isinstance(data, dict):
        if isinstance(data.get("embedding"), list):
            return [float(v) for v in data["embedding"]]
        items = data.get("data")
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict) and isinstance(first.get("embedding"), list):
                return [float(v) for v in first["embedding"]]
    return []
