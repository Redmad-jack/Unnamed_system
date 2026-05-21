from __future__ import annotations

import asyncio
from types import SimpleNamespace

from conscious_entity.expression.output_model import ExpressionOutput
from conscious_entity.interfaces import api
from conscious_entity.interfaces.api_models import DialogRequest, PresentationLatencyRequest
from conscious_entity.telemetry.latency import reset_latency_tracker_for_tests


class FakeLoop:
    def run_turn(self, text, source="dialog", input_metadata=None):
        return ExpressionOutput(
            text="我会回应。",
            spoken_text=None,
            delay_ms=100,
            visual_mode="normal",
            raw_prompt="prompt",
            latency_record_id="turn_fake",
        )


def _request():
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        loop=FakeLoop(),
        loop_lock=asyncio.Lock(),
        identity_gating=None,
        vision_manager=None,
    )))


def test_dialog_response_includes_latency_record_id():
    result = asyncio.run(api.dialog(DialogRequest(text="你好"), _request()))

    assert result["latency_record_id"] == "turn_fake"


def test_presentation_latency_api_writes_and_reads_records(tmp_path):
    reset_latency_tracker_for_tests(tmp_path)

    created = asyncio.run(api.stats_presentation_latency_record(
        PresentationLatencyRequest(
            kind="dashboard.text_dialog.render",
            duration_ms=12.5,
            latency_record_id="turn_fake",
            metadata={"surface": "dashboard"},
        )
    ))
    result = asyncio.run(api.stats_presentation_latency(n=50))

    assert created["latency_record_id"] == "turn_fake"
    assert result["summary"]["total_records"] == 1
    assert result["recent"][0]["kind"] == "dashboard.text_dialog.render"
    assert result["recent"][0]["metadata"]["surface"] == "dashboard"
