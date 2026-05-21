from __future__ import annotations

from datetime import datetime

from conscious_entity.llm.stats_tracker import LLMCallRecord, LLMStatsTracker
from conscious_entity.memory.retrieval import MemoryRetriever
from conscious_entity.telemetry.latency import (
    AudioLatencyRecord,
    LatencyTracker,
    PresentationLatencyRecord,
    TurnLatencyRecord,
    TurnLatencyRecorder,
    activate_turn_recorder,
    current_turn_recorder,
    record_audio_latency,
    reset_latency_tracker_for_tests,
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
    reset_latency_tracker_for_tests()
    record_audio_latency("test.latency", 1.5, metadata={"source": "unit"})


def test_jsonl_latency_store_keeps_recent_50_and_restores(tmp_path):
    tracker = LatencyTracker(storage_dir=tmp_path)
    for idx in range(55):
        tracker.record_turn(_turn_record(idx))
        tracker.record_audio(_audio_record(f"audio.{idx}", float(idx)))
        tracker.record_presentation(_presentation_record(idx))

    reloaded = LatencyTracker(storage_dir=tmp_path)

    assert len(reloaded.recent_turns(100)) == 50
    assert len(reloaded.recent_audio(100)) == 50
    assert len(reloaded.recent_presentation(100)) == 50
    assert reloaded.recent_turns(100)[0].record_id == "turn_5"
    assert reloaded.recent_audio(100)[0].record_id == "audio.5-id"
    assert reloaded.recent_presentation(100)[0].record_id == "presentation_5"


def test_llm_jsonl_store_keeps_recent_50_and_restores(tmp_path):
    tracker = LLMStatsTracker(storage_dir=tmp_path)
    for idx in range(55):
        tracker.record(
            LLMCallRecord(
                timestamp=datetime.fromisoformat("2026-05-11T00:00:00"),
                model=f"model-{idx}",
                duration_ms=idx,
                success=True,
                prompt_tokens=idx,
                completion_tokens=idx + 1,
            )
        )

    reloaded = LLMStatsTracker(storage_dir=tmp_path)

    assert len(reloaded.recent(100)) == 50
    assert reloaded.recent(100)[0].model == "model-5"
    assert reloaded.summary()["total_calls"] == 50


def test_jsonl_store_skips_bad_lines(tmp_path):
    (tmp_path / "turn-latency.jsonl").write_text(
        "{bad json}\n"
        '{"record_id":"turn_ok","source":"dialog","timestamp":"2026-05-11T00:00:00+00:00",'
        '"total_ms":12.0,"success":true,"error":null,"metadata":{},"steps":[]}\n',
        encoding="utf-8",
    )

    tracker = LatencyTracker(storage_dir=tmp_path)

    assert [record.record_id for record in tracker.recent_turns()] == ["turn_ok"]


def test_memory_retrieval_substeps_enter_turn_latency(in_memory_db):
    in_memory_db.execute("INSERT INTO sessions (id) VALUES (?)", ("session-1",))
    in_memory_db.execute(
        """
        INSERT INTO interaction_log (
            session_id, role, raw_text, event_types, policy_action, expression_output
        ) VALUES (?, 'user', ?, '[]', 'respond_openly', ?)
        """,
        ("session-1", "你记得我吗", "我看到刚才的问题。"),
    )
    in_memory_db.commit()
    recorder = TurnLatencyRecorder(source="dialog")

    with activate_turn_recorder(recorder):
        MemoryRetriever(in_memory_db, "session-1").retrieve("你记得吗")

    step_names = {step.name for step in recorder.finish().steps}
    assert "memory_retrieval.deterministic" in step_names
    assert "memory_retrieval.current_session_recent_dialog" in step_names
    assert "memory_retrieval.current_episodic" in step_names
    assert "memory_retrieval.reflective" in step_names


def _audio_record(kind: str, duration_ms: float):
    return AudioLatencyRecord(
        record_id=f"{kind}-id",
        kind=kind,
        timestamp="2026-05-11T00:00:00+00:00",
        duration_ms=duration_ms,
    )


def _turn_record(idx: int) -> TurnLatencyRecord:
    return TurnLatencyRecord(
        record_id=f"turn_{idx}",
        source="dialog",
        timestamp="2026-05-11T00:00:00+00:00",
        total_ms=float(idx),
        success=True,
        error=None,
        metadata={"idx": idx},
        steps=[],
    )


def _presentation_record(idx: int) -> PresentationLatencyRecord:
    return PresentationLatencyRecord(
        record_id=f"presentation_{idx}",
        kind="dashboard.text_dialog.render",
        timestamp="2026-05-11T00:00:00+00:00",
        duration_ms=float(idx),
        latency_record_id=f"turn_{idx}",
    )
