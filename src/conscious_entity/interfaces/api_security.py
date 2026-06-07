from __future__ import annotations

import os
import secrets
from typing import Iterable

from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send


PUBLIC_PATH_PREFIX = "/api/v1/public"
PUBLIC_PATHS = {"/health"}


def env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def online_public_mode() -> bool:
    return env_flag("ONLINE_PUBLIC_MODE", default=False)


def allowed_public_origins() -> list[str]:
    raw = os.getenv("STRANGER_PUBLIC_ALLOWED_ORIGINS", "")
    return [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]


def configure_cors(app) -> None:
    origins = allowed_public_origins()
    if not origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Session-Token", "X-Operator-Api-Key"],
    )


def is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PATH_PREFIX)


def origin_allowed(origin: str | None, *, allowed: Iterable[str] | None = None) -> bool:
    origins = list(allowed if allowed is not None else allowed_public_origins())
    if not origins:
        return True
    if not origin:
        return False
    cleaned = origin.strip().rstrip("/")
    return cleaned in origins


def operator_authorized(headers, query_string: bytes = b"") -> bool:
    expected = os.getenv("OPERATOR_API_KEY")
    if not expected:
        return False

    candidates: list[str] = []
    direct = headers.get("X-Operator-Api-Key") or headers.get("x-operator-api-key")
    if direct:
        candidates.append(direct)

    auth = headers.get("Authorization") or headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        candidates.append(auth[7:].strip())

    if query_string:
        for part in query_string.decode("utf-8", errors="ignore").split("&"):
            key, _, value = part.partition("=")
            if key in {"operator_token", "operator_api_key"} and value:
                candidates.append(value)

    return any(secrets.compare_digest(candidate, expected) for candidate in candidates)


class OnlinePublicModeMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope.get("type")
        if scope_type not in {"http", "websocket"} or not online_public_mode():
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "")
        if is_public_path(path):
            await self.app(scope, receive, send)
            return

        headers = _scope_headers(scope)
        if operator_authorized(headers, scope.get("query_string", b"")):
            await self.app(scope, receive, send)
            return

        if scope_type == "websocket":
            await send({"type": "websocket.close", "code": 1008, "reason": "operator authorization required"})
            return

        body = b'{"detail":"operator authorization required"}'
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _scope_headers(scope: Scope) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw_key, raw_value in scope.get("headers", []):
        key = raw_key.decode("latin1")
        value = raw_value.decode("latin1")
        headers[key] = value
        headers[key.lower()] = value
    return headers
