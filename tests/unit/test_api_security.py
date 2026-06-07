from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from conscious_entity.interfaces.api_security import (
    OnlinePublicModeMiddleware,
    origin_allowed,
)


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(OnlinePublicModeMiddleware)

    @app.get("/")
    async def dashboard():
        return {"ok": True}

    @app.get("/api/v1/public/ping")
    async def public_ping():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    return app


def test_online_public_mode_blocks_operator_routes_without_key(monkeypatch):
    monkeypatch.setenv("ONLINE_PUBLIC_MODE", "1")
    monkeypatch.setenv("OPERATOR_API_KEY", "operator-secret")

    client = TestClient(_app())

    assert client.get("/").status_code == 401
    assert client.get("/api/v1/public/ping").status_code == 200
    assert client.get("/health").status_code == 200


def test_online_public_mode_allows_operator_key(monkeypatch):
    monkeypatch.setenv("ONLINE_PUBLIC_MODE", "1")
    monkeypatch.setenv("OPERATOR_API_KEY", "operator-secret")

    client = TestClient(_app())

    response = client.get("/", headers={"Authorization": "Bearer operator-secret"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_online_public_mode_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ONLINE_PUBLIC_MODE", raising=False)
    monkeypatch.setenv("OPERATOR_API_KEY", "operator-secret")

    client = TestClient(_app())

    assert client.get("/").status_code == 200


def test_public_origin_allowlist(monkeypatch):
    monkeypatch.setenv(
        "STRANGER_PUBLIC_ALLOWED_ORIGINS",
        "https://stranger.example.net, https://other.example.net/",
    )

    assert origin_allowed("https://stranger.example.net")
    assert origin_allowed("https://other.example.net")
    assert not origin_allowed("https://unknown.example.net")
    assert not origin_allowed(None)
