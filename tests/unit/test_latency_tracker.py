from __future__ import annotations

from conscious_entity.telemetry.latency import (
    LatencyTracker,
    TurnLatencyRecorder,
    activate_turn_recorder,
    current_turn_recorder,
    record_audio_latency,
    turn_step,
)


def test_turn_latency_recorder_collects_steps():
    tracker = LatencyTracker()
    recorder = TurnLatencyRecorder(source="dialog", metadata={"input_chars": 5})

    with activate_turn_recorder(recorder):
        assert current_turn_recorder() is recorder
        with turn_step("expression.llm", metadata={"max_tokens": 120}):
            pass

    record = recorder.finish(success=True)
    tracker.record_turn(record)
    summary = tracker.turn_summary()

    assert summary["total_turns"] == 1
    assert summary["success_count"] == 1
    assert "expression.llm" in summary["steps"]
    assert tracker.recent_turns(1)[0].to_public_dict()["metadata"]["input_chars"] == 5


def test_audio_latency_summary_groups_by_kind():
    tracker = LatencyTracker()
    tracker.record_audio(record_audio := _audio_record("tts.first_byte", 10.0))
    tracker.record_audio(_audio_record("tts.first_byte", 30.0))
    tracker.record_audio(_audio_record("stt.final", 50.0))

    summary = tracker.audio_summary()

    assert record_audio.kind == "tts.first_byte"
    assert summary["total_records"] == 3
    assert summary["kinds"]["tts.first_byte"]["count"] == 2
    assert summary["kinds"]["tts.first_byte"]["avg_ms"] == 20.0


def test_record_audio_latency_uses_global_tracker():
    record_audio_latency("test.latency", 1.5, metadata={"source": "unit"})


def _audio_record(kind: str, duration_ms: float):
    from conscious_entity.telemetry.latency import AudioLatencyRecord

    return AudioLatencyRecord(
        record_id=f"{kind}-id",
        kind=kind,
        timestamp="2026-05-11T00:00:00+00:00",
        duration_ms=duration_ms,
    )
