from __future__ import annotations

import pytest

from conscious_entity.llm.embedding_client import (
    EmbeddingClient,
    EmbeddingConfigurationError,
    _extract_embedding,
)


def test_embedding_client_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENTITY_EMBEDDING_MODE", raising=False)
    client = EmbeddingClient.from_env()
    assert client.enabled is False


def test_embedding_client_requires_complete_openai_compatible_config(monkeypatch):
    monkeypatch.setenv("ENTITY_EMBEDDING_MODE", "openai_compatible")
    monkeypatch.delenv("ENTITY_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("ENTITY_EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("ENTITY_EMBEDDING_BASE_URL", raising=False)
    monkeypatch.delenv("ENTITY_EMBEDDING_ENDPOINT", raising=False)

    with pytest.raises(EmbeddingConfigurationError):
        EmbeddingClient.from_env()


def test_extract_embedding_from_openai_compatible_response():
    data = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
    assert _extract_embedding(data) == [0.1, 0.2, 0.3]


def test_extract_embedding_from_flat_response():
    data = {"embedding": [1, 2, 3]}
    assert _extract_embedding(data) == [1.0, 2.0, 3.0]
