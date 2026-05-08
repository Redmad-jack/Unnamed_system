#!/usr/bin/env python3
"""
Diagnose Doubao realtime dialogue handshake variants.

The script only reads local environment variables, opens Doubao WebSocket
connections, and prints scrubbed protocol events. It does not touch project data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import websockets

from conscious_entity.runtime_env import load_project_env
from have_some_ai.voice_realtime import (
    DOUBAO_CHAT_TTS_TEXT,
    DOUBAO_CHAT_TEXT_QUERY,
    DOUBAO_CONNECTION_STARTED,
    DOUBAO_SAY_HELLO,
    DOUBAO_START_CONNECTION,
    DOUBAO_START_SESSION,
    DoubaoProtocol,
    DoubaoRealtimeConfig,
    build_doubao_start_session_payload,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnose Doubao realtime dialogue StartSession variants."
    )
    parser.add_argument(
        "--variant",
        choices=[variant["name"] for variant in _variants_placeholder()],
        help="Run one variant instead of the full handshake matrix.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="Seconds to wait for each provider frame.",
    )
    parser.add_argument(
        "--probe-mode",
        choices=["none", "say_hello", "chat_text_query", "chat_tts_text"],
        default="none",
        help="Optional post-StartSession probe to test greeting, text dialogue, or direct TTS.",
    )
    parser.add_argument(
        "--probe-text",
        default="你好，请用一句话回答我听得到你。",
        help="Text used by --probe-mode.",
    )
    args = parser.parse_args()

    load_project_env()
    config = DoubaoRealtimeConfig.from_env()
    variants = _build_variants(config)
    if args.variant:
        variants = [variant for variant in variants if variant["name"] == args.variant]

    print("Doubao realtime dialogue diagnostic")
    print(f"ws_url: {config.ws_url}")
    print(f"resource_id: {config.resource_id}")
    print(f"app_id: {_redact(config.app_id)}")
    print(f"app_key: {_redact(config.app_key)}")
    print(f"access_token: {_redact(config.access_token)}")
    print(f"model: {config.dialog_model}")
    print(f"speaker: {config.speaker}")
    print("")

    asyncio.run(_run_matrix(
        config,
        variants,
        args.timeout,
        args.probe_mode,
        args.probe_text.strip(),
    ))


async def _run_matrix(
    config: DoubaoRealtimeConfig,
    variants: list[dict[str, Any]],
    timeout: float,
    probe_mode: str,
    probe_text: str,
) -> None:
    for index, variant in enumerate(variants, start=1):
        print(f"== {index}. {variant['name']} ==")
        await _run_variant(config, variant, timeout, probe_mode, probe_text)
        print("")


async def _run_variant(
    config: DoubaoRealtimeConfig,
    variant: dict[str, Any],
    timeout: float,
    probe_mode: str,
    probe_text: str,
) -> None:
    connect_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    headers = config.headers(connect_id)

    ws = None
    try:
        ws = await _connect(config.ws_url, headers)
        log_id = _response_header(ws, "X-Tt-Logid")
        print(f"connect_id: {connect_id}")
        print(f"session_id: {session_id}")
        print(f"X-Tt-Logid: {log_id or '(not returned)'}")

        await ws.send(DoubaoProtocol.encode_json(DOUBAO_START_CONNECTION, {}))
        connection = await _recv_decoded(ws, timeout)
        _print_frame("recv StartConnection", connection)
        if connection["frame"].get("event") != DOUBAO_CONNECTION_STARTED:
            return

        payload = variant["payload"]
        print("StartSession payload:")
        print(json.dumps(_scrub(payload), ensure_ascii=False, indent=2))
        await ws.send(DoubaoProtocol.encode_json(
            DOUBAO_START_SESSION,
            payload,
            session_id=session_id,
        ))
        session = await _recv_decoded(ws, timeout)
        _print_frame("recv StartSession", session)

        if session["frame"].get("event") != 150 or probe_mode == "none" or not probe_text:
            return

        if probe_mode == "say_hello":
            await ws.send(DoubaoProtocol.encode_json(
                DOUBAO_SAY_HELLO,
                {"content": probe_text},
                session_id=session_id,
            ))
            print(f"sent SayHello: {probe_text}")
        elif probe_mode == "chat_text_query":
            await ws.send(DoubaoProtocol.encode_json(
                DOUBAO_CHAT_TEXT_QUERY,
                {"content": probe_text},
                session_id=session_id,
            ))
            print(f"sent ChatTextQuery: {probe_text}")
        else:
            await ws.send(DoubaoProtocol.encode_json(
                DOUBAO_CHAT_TTS_TEXT,
                {"start": True, "content": probe_text, "end": False},
                session_id=session_id,
            ))
            await ws.send(DoubaoProtocol.encode_json(
                DOUBAO_CHAT_TTS_TEXT,
                {"start": False, "content": "", "end": True},
                session_id=session_id,
            ))
            print(f"sent ChatTTSText: {probe_text}")
        for _ in range(8):
            event = await _recv_decoded(ws, timeout)
            _print_frame("recv probe", event)
            frame_event = event["frame"].get("event")
            if frame_event in {352, 359, 559, 599} or event["frame"].get("error"):
                if frame_event in {359, 559, 599} or event["frame"].get("error"):
                    return
    except asyncio.TimeoutError:
        print(f"timeout after {timeout:.1f}s")
    except Exception as exc:
        print(f"exception: {_scrub_text(str(exc))}")
    finally:
        if ws is not None:
            close = getattr(ws, "close", None)
            if close is not None:
                await close()


async def _connect(url: str, headers: dict[str, str]) -> Any:
    try:
        return await websockets.connect(url, additional_headers=headers, max_size=None)
    except TypeError:
        return await websockets.connect(url, extra_headers=headers, max_size=None)


async def _recv_decoded(ws: Any, timeout: float) -> dict[str, Any]:
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    raw_bytes = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
    frame = DoubaoProtocol.decode_frame(raw)
    return {
        "frame": frame,
        "raw_len": len(raw_bytes),
        "raw_hex_prefix": raw_bytes[:16].hex(" "),
    }


def _print_frame(label: str, decoded: dict[str, Any]) -> None:
    frame = _scrub(decoded["frame"])
    print(f"{label}:")
    print(json.dumps({
        "frame": frame,
        "raw_len": decoded["raw_len"],
        "raw_hex_prefix": decoded["raw_hex_prefix"],
    }, ensure_ascii=False, indent=2))


def _build_variants(config: DoubaoRealtimeConfig) -> list[dict[str, Any]]:
    return [
        {
            "name": "full_push_to_talk_pcm",
            "payload": build_doubao_start_session_payload(
                config,
                input_mod="push_to_talk",
            ),
        },
        {
            "name": "full_server_vad_pcm",
            "payload": build_doubao_start_session_payload(
                config,
                input_mod=None,
            ),
        },
        {
            "name": "full_keep_alive_pcm",
            "payload": build_doubao_start_session_payload(
                config,
                input_mod="keep_alive",
            ),
        },
        {
            "name": "full_text_mode_pcm",
            "payload": build_doubao_start_session_payload(
                config,
                input_mod="text",
            ),
        },
        {
            "name": "full_push_to_talk_default_ogg",
            "payload": build_doubao_start_session_payload(
                config,
                input_mod="push_to_talk",
                include_audio_config=False,
            ),
        },
        {
            "name": "full_push_to_talk_without_audio_info",
            "payload": build_doubao_start_session_payload(
                config,
                input_mod="push_to_talk",
                include_audio_info=False,
            ),
        },
        {
            "name": "full_push_to_talk_without_empty_extras",
            "payload": build_doubao_start_session_payload(
                config,
                input_mod="push_to_talk",
                include_empty_extras=False,
            ),
        },
        {
            "name": "minimal_doc_dialog_extra_null",
            "payload": {
                "dialog": {
                    "bot_name": config.bot_name,
                    "dialog_id": "",
                    "extra": None,
                },
            },
        },
    ]


def _variants_placeholder() -> list[dict[str, Any]]:
    return [
        {"name": "full_push_to_talk_pcm"},
        {"name": "full_server_vad_pcm"},
        {"name": "full_keep_alive_pcm"},
        {"name": "full_text_mode_pcm"},
        {"name": "full_push_to_talk_default_ogg"},
        {"name": "full_push_to_talk_without_audio_info"},
        {"name": "full_push_to_talk_without_empty_extras"},
        {"name": "minimal_doc_dialog_extra_null"},
    ]


def _response_header(ws: Any, name: str) -> str | None:
    response = getattr(ws, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        headers = getattr(ws, "response_headers", None)
    if headers is None:
        return None
    getter = getattr(headers, "get", None)
    if getter is None:
        return None
    value = getter(name) or getter(name.lower())
    return str(value) if value else None


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in {"audio", "audio_base64", "payload_audio"}:
                result[key_text] = "[audio omitted]"
            else:
                result[key_text] = _scrub(item)
        return result
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, str):
        return _scrub_text(value)
    return value


def _scrub_text(text: str) -> str:
    scrubbed = text
    for secret in (
        os.getenv("HAVE_SOME_AI_DOUBAO_APP_ID"),
        os.getenv("HAVE_SOME_AI_DOUBAO_APP_KEY"),
        os.getenv("HAVE_SOME_AI_DOUBAO_ACCESS_TOKEN"),
    ):
        if secret:
            scrubbed = scrubbed.replace(secret, "[redacted]")
    return scrubbed


def _redact(value: str | None, keep: int = 4) -> str:
    if not value:
        return "(not set)"
    if len(value) <= keep * 2:
        return "***"
    return f"{value[:keep]}...{value[-keep:]}"


if __name__ == "__main__":
    main()
