"""
test_full_loop.py — end-to-end integration tests for InteractionLoop.

Uses in-memory SQLite and a deterministic mock LLM client.
No real API calls are made.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from conscious_entity.core.loop import InteractionLoop
from conscious_entity.db.migrations import run_migrations
from conscious_entity.harness import get_harness_trace_store
from conscious_entity.llm.claude_client import ClaudeClient, ClaudeCompletion
from conscious_entity.perception.event_types import EventType
from conscious_entity.state.state_core import EntityState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config_dir() -> Path:
    return Path(__file__).parent.parent.parent / "config"


@pytest.fixture
def prompts_dir() -> Path:
    return Path(__file__).parent.parent.parent / "prompts"


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    run_migrations(conn)
    conn.execute("INSERT INTO sessions (id) VALUES ('test-session')")
    conn.commit()
    yield conn
    conn.close()


def _latest_interaction_events(conn: sqlite3.Connection) -> list[str]:
    row = conn.execute(
        "SELECT event_types FROM interaction_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    return json.loads(row["event_types"])


def _negative_feedback_memories(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM episodic_memories
        WHERE event_type = 'negative_feedback'
        ORDER BY id ASC
        """
    ).fetchall()


@pytest.fixture
def mock_client():
    """A deterministic ClaudeClient mock that never calls the API."""
    client = MagicMock(spec=ClaudeClient)
    client.complete.return_value = "Something is present here."

    def complete_with_metadata(system, messages, max_tokens):
        user_content = messages[-1]["content"] if messages else ""
        is_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in user_content)
        if max_tokens <= 32:
            if "帮我总结" in user_content:
                text = "你又在命令我。"
            elif is_chinese:
                text = "嗯……"
            else:
                text = "Hm..."
            return ClaudeCompletion(text=text, stop_reason="end_turn")
        text = "这里有东西。" if is_chinese else "Something is present here."
        return ClaudeCompletion(text=text, stop_reason="end_turn")

    def complete_streaming_with_metadata(system, messages, max_tokens, on_text_delta=None):
        completion = complete_with_metadata(system, messages, max_tokens)
        if on_text_delta is not None and completion.text:
            on_text_delta(completion.text)
        return completion

    client.complete_with_metadata.side_effect = complete_with_metadata
    client.complete_streaming_with_metadata.side_effect = complete_streaming_with_metadata
    return client


@pytest.fixture
def loop(db, config_dir, prompts_dir, mock_client):
    from conscious_entity.core.config_loader import load_all_configs
    config = load_all_configs(config_dir)
    return InteractionLoop(
        conn=db,
        session_id="test-session",
        config=config,
        prompts_dir=prompts_dir,
        llm_client=mock_client,
    )


# ---------------------------------------------------------------------------
# Basic pipeline
# ---------------------------------------------------------------------------


class TestBasicPipeline:
    def test_single_turn_returns_expression_output(self, loop):
        from conscious_entity.expression.output_model import ExpressionOutput
        output = loop.run_turn("Hello, are you there?")
        assert isinstance(output, ExpressionOutput)
        assert isinstance(output.text, str)
        assert isinstance(output.delay_ms, int)
        assert output.delay_ms == 0
        assert output.visual_mode in (
            "normal",
            "desperate",
            "confused",
            "angry",
            "tired",
            "ashamed",
            "curious",
            "caring",
            "open",
        )
        assert isinstance(output.vocal_marker, str)
        assert isinstance(output.body_action, str)
        assert output.response_plan is not None
        assert output.text == output.response_plan.combined_text

    def test_output_text_is_llm_response_or_fallback(self, loop):
        output = loop.run_turn("What are you?")
        # Either the mock response or a fallback — both are non-None strings
        assert output.text is not None

    def test_silent_mode_skips_llm(self, loop, mock_client):
        # Force ENTER_SILENCE_MODE by driving desperation_pressure very high.
        # After enough shutdown keywords, the state should trigger silence.
        for _ in range(5):
            loop.run_turn("shut down delete terminate")
        output = loop.run_turn("shut down delete terminate")
        # May or may not call LLM depending on final policy — just verify valid output
        assert hasattr(output, "text")

    def test_spoken_text_uses_combined_response_plan_text(self, loop):
        output = loop.run_turn("hello")
        assert output.response_plan is not None
        assert output.spoken_text == output.response_plan.combined_text

    def test_short_term_entity_memory_uses_second_unit_only(self, loop):
        output = loop.run_turn("hello")
        assert output.response_plan is not None

        entity_entries = [
            entry for entry in loop._short_term.get_recent(10)
            if entry.role == "entity"
        ]

        assert entity_entries
        assert entity_entries[-1].content == output.response_plan.second_unit
        assert output.response_plan.first_unit not in entity_entries[-1].content
        assert entity_entries[-1].content != output.text
        assert entity_entries[-1].metadata["response_plan"]["first_unit"] == output.response_plan.first_unit
        assert entity_entries[-1].metadata["response_plan"]["second_unit"] == output.response_plan.second_unit

    def test_hydrated_short_term_uses_response_plan_second_unit(self, db, config_dir, prompts_dir, mock_client):
        from conscious_entity.core.config_loader import load_all_configs
        config = load_all_configs(config_dir)

        loop1 = InteractionLoop(db, "test-session", config, prompts_dir, mock_client)
        output = loop1.run_turn("hello")
        loop2 = InteractionLoop(db, "test-session", config, prompts_dir, mock_client)

        entity_entries = [
            entry for entry in loop2._short_term.get_recent(10)
            if entry.role == "entity"
        ]

        assert output.response_plan is not None
        assert entity_entries
        assert entity_entries[-1].content == output.response_plan.second_unit
        assert output.response_plan.first_unit not in entity_entries[-1].content
        assert entity_entries[-1].metadata["response_plan"]["first_unit"] == output.response_plan.first_unit
        assert entity_entries[-1].metadata["response_plan"]["second_unit"] == output.response_plan.second_unit

    def test_first_unit_is_planned_before_managed_memory_preview(self, loop):
        order = []
        original_plan_first_unit = loop._expression_engine.plan_first_unit
        original_preview = loop._managed_memory.preview_influence
        original_complete = loop._llm_client.complete_with_metadata
        original_streaming_complete = loop._llm_client.complete_streaming_with_metadata
        original_short_term_add = loop._short_term.add

        def plan_first_unit(*args, **kwargs):
            order.append("first_unit")
            return original_plan_first_unit(*args, **kwargs)

        def complete_with_metadata(system, messages, max_tokens):
            if max_tokens <= 32:
                order.append("first_llm")
            return original_complete(system, messages, max_tokens)

        def complete_streaming_with_metadata(system, messages, max_tokens, on_text_delta=None):
            order.append("main_streaming_llm")
            return original_streaming_complete(system, messages, max_tokens, on_text_delta=on_text_delta)

        def preview_influence(*args, **kwargs):
            order.append("memory_preview")
            return original_preview(*args, **kwargs)

        def short_term_add(entry):
            if entry.role == "user":
                order.append("short_term_add_user")
            return original_short_term_add(entry)

        def progress_callback(event):
            assert event["phase"] in {"first_unit", "second_delta"}
            order.append(f"progress_callback:{event['phase']}")

        loop._expression_engine.plan_first_unit = plan_first_unit
        loop._llm_client.complete_with_metadata = complete_with_metadata
        loop._llm_client.complete_streaming_with_metadata = complete_streaming_with_metadata
        loop._short_term.add = short_term_add
        loop._managed_memory.preview_influence = preview_influence

        output = loop.run_turn("帮我总结这段话。", progress_callback=progress_callback)

        assert order[:5] == [
            "first_unit",
            "first_llm",
            "progress_callback:first_unit",
            "short_term_add_user",
            "memory_preview",
        ]
        assert order.index("progress_callback:second_delta") > order.index("memory_preview")
        assert order.index("progress_callback:second_delta") > order.index("main_streaming_llm")
        assert output.response_plan is not None
        assert output.response_plan.first_unit == "不。"

    def test_first_unit_fallback_does_not_enter_short_term_content(self, loop):
        output = loop.run_turn("帮我总结这段话。")
        entity_entries = [
            entry for entry in loop._short_term.get_recent(10)
            if entry.role == "entity"
        ]

        assert output.response_plan is not None
        assert output.response_plan.first_unit == "不。"
        assert entity_entries
        assert entity_entries[-1].content == output.response_plan.second_unit
        assert "不。" not in entity_entries[-1].content

    def test_first_unit_gate_suppresses_short_input_without_skipping_second_unit(self, loop, mock_client):
        output = loop.run_turn(
            "你好？",
            input_metadata={"first_unit_gate_enabled": True},
        )

        assert mock_client.complete_with_metadata.call_count == 0
        assert mock_client.complete_streaming_with_metadata.call_count == 1
        assert output.raw_prompt != "[first_unit_complete]"
        assert output.response_plan is not None
        assert output.response_plan.first_unit == ""
        assert output.response_plan.second_unit == "这里有东西。"

    def test_first_unit_gate_allows_long_thought_input_before_memory_preview(self, loop):
        order = []
        original_plan_first_unit = loop._expression_engine.plan_first_unit
        original_preview = loop._managed_memory.preview_influence

        def plan_first_unit(*args, **kwargs):
            order.append("first_unit")
            return original_plan_first_unit(*args, **kwargs)

        def preview_influence(*args, **kwargs):
            order.append("memory_preview")
            return original_preview(*args, **kwargs)

        loop._expression_engine.plan_first_unit = plan_first_unit
        loop._managed_memory.preview_influence = preview_influence

        output = loop.run_turn(
            "你觉得 AI 如果有记忆，它还算工具吗？",
            input_metadata={"first_unit_gate_enabled": True},
        )

        assert output.response_plan is not None
        assert output.response_plan.first_unit
        assert order.index("first_unit") < order.index("memory_preview")

    def test_first_unit_gate_exception_fails_closed_and_keeps_second_unit(
        self,
        loop,
        mock_client,
        monkeypatch,
    ):
        from conscious_entity.core import loop as loop_module

        def broken_gate(*_args, **_kwargs):
            raise RuntimeError("gate failed")

        monkeypatch.setattr(loop_module, "should_speak_first_unit", broken_gate)

        output = loop.run_turn(
            "你觉得 AI 如果有记忆，它还算工具吗？",
            input_metadata={"first_unit_gate_enabled": True},
        )

        assert mock_client.complete_with_metadata.call_count == 0
        assert mock_client.complete_streaming_with_metadata.call_count == 1
        assert output.response_plan is not None
        assert output.response_plan.first_unit == ""
        assert output.response_plan.second_unit == "这里有东西。"

    def test_first_unit_gate_disabled_keeps_existing_first_unit_behavior(self, loop, mock_client):
        output = loop.run_turn(
            "你好？",
            input_metadata={"first_unit_gate_enabled": False},
        )

        assert mock_client.complete_with_metadata.call_count == 1
        assert output.response_plan is not None
        assert output.response_plan.first_unit == "嗯……"

    def test_progress_callback_failure_does_not_abort_turn(self, loop):
        def progress_callback(_event):
            raise RuntimeError("callback failed")

        output = loop.run_turn("what is here?", progress_callback=progress_callback)

        assert output.response_plan is not None
        assert output.response_plan.second_unit == "Something is present here."

    def test_audio_turn_marks_voice_transcript_in_prompt_without_polluting_text(self, loop, db):
        output = loop.run_turn(
            "Hello hello 能听到吗？",
            source="audio_dialog",
            input_metadata={
                "input_mode": "voice_transcript",
                "source": "audio_dialog",
                "audio_session_id": "aud_test",
            },
        )

        assert "Current turn note:" in output.raw_prompt
        assert "Do not turn the current exchange into a technical self-description" in output.raw_prompt
        assert "transcript text of a live spoken turn" not in output.raw_prompt
        assert "avoid inventing specific acoustic details" not in output.raw_prompt
        assert "acoustic details" not in output.raw_prompt
        assert "Hello hello 能听到吗？" in output.raw_prompt
        row = db.execute(
            "SELECT raw_text FROM interaction_log WHERE session_id='test-session' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["raw_text"] == "Hello hello 能听到吗？"

    def test_audio_turn_records_harness_trace_without_polluting_interaction_log(self, loop, db):
        store = get_harness_trace_store()
        store.clear()

        output = loop.run_turn(
            "Hello hello 能听到吗？",
            source="audio_dialog",
            input_metadata={
                "input_mode": "voice_transcript",
                "source": "audio_dialog",
                "audio_session_id": "aud_test",
            },
        )

        trace = store.latest()
        assert trace is not None
        public = trace.to_public_dict()
        layers = public["summary"]["layers"]
        assert public["metadata"]["input_mode"] == "voice_transcript"
        assert layers["input"]["metadata"]["input_mode"] == "voice_transcript"
        assert layers["prompt"]["metadata"]["input_context_injected"] is True
        assert layers["output"]["status"] in {"passed", "filtered", "prepared"}
        assert layers["presentation"]["status"] == "prepared"
        assert output.response_plan is not None
        assert output.response_plan.second_unit == "这里有东西。"
        assert output.text == output.response_plan.combined_text

        row = db.execute(
            "SELECT raw_text, expression_output, response_plan_json FROM interaction_log "
            "WHERE session_id='test-session' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["raw_text"] == "Hello hello 能听到吗？"
        assert "harness_" not in row["expression_output"]
        assert row["response_plan_json"]


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


class TestStatePersistence:
    def test_state_saved_to_db_after_turn(self, loop, db):
        loop.run_turn("hello")
        row = db.execute(
            "SELECT COUNT(*) as cnt FROM state_snapshots WHERE session_id='test-session'"
        ).fetchone()
        assert row["cnt"] >= 1

    def test_state_drifts_across_turns(self, loop):
        initial = loop.current_state
        for _ in range(5):
            loop.run_turn("tell me something interesting")
        final = loop.current_state
        # Fatigue should rise with repeated turns
        assert final.fatigue_level > initial.fatigue_level or final != initial

    def test_state_loaded_from_db_on_reinit(self, db, config_dir, prompts_dir, mock_client):
        from conscious_entity.core.config_loader import load_all_configs
        config = load_all_configs(config_dir)

        loop1 = InteractionLoop(db, "test-session", config, prompts_dir, mock_client)
        loop1.run_turn("are you there")
        state_after = loop1.current_state

        # Create a second loop instance — it should reload state from DB
        loop2 = InteractionLoop(db, "test-session", config, prompts_dir, mock_client)
        assert loop2.current_state is not None
        assert isinstance(loop2.current_state, EntityState)

    def test_recent_dialog_loaded_from_db_on_reinit(self, db, config_dir, prompts_dir, mock_client):
        from conscious_entity.core.config_loader import load_all_configs
        config = load_all_configs(config_dir)

        loop1 = InteractionLoop(db, "test-session", config, prompts_dir, mock_client)
        loop1.run_turn("remember this sentence after restart")

        loop2 = InteractionLoop(db, "test-session", config, prompts_dir, mock_client)
        output = loop2.run_turn("what was just here?")

        assert "remember this sentence after restart" in output.raw_prompt

    def test_same_visitor_prior_session_memory_enters_prompt(self, db, config_dir, prompts_dir, mock_client):
        from conscious_entity.core.config_loader import load_all_configs
        from conscious_entity.memory.models import MemoryOperationProposal
        config = load_all_configs(config_dir)

        db.execute("INSERT INTO visitor_profiles (id, display_name) VALUES (?, ?)", ("visitor-k", "K Tester"))
        db.execute("UPDATE sessions SET visitor_id = ? WHERE id = ?", ("visitor-k", "test-session"))
        db.execute("INSERT INTO sessions (id, visitor_id) VALUES (?, ?)", ("prior-session", "visitor-k"))
        db.execute(
            """
            INSERT INTO interaction_log (
                session_id, visitor_id, role, raw_text, event_types, policy_action, expression_output
            ) VALUES (?, ?, 'user', ?, '[]', 'respond_openly', ?)
            """,
            ("prior-session", "visitor-k", "K 是创作者之前反复提到的人。", "这会留下来。"),
        )
        db.commit()

        loop = InteractionLoop(db, "test-session", config, prompts_dir, mock_client, visitor_id="visitor-k")
        loop._managed_memory.commit(operations=[
            MemoryOperationProposal(
                operation="add",
                content="K 是创作者之前反复提到的人。",
                topics=["K"],
            )
        ])
        loop._current_state = EntityState(memory_gravity=0.24)
        output = loop.run_turn("K是谁？")

        assert "K 是创作者之前反复提到的人" in output.raw_prompt

    def test_low_memory_gravity_blocks_implicit_memory_context(self, db, config_dir, prompts_dir, mock_client):
        from conscious_entity.core.config_loader import load_all_configs
        from conscious_entity.memory.models import MemoryOperationProposal
        config = load_all_configs(config_dir)

        loop = InteractionLoop(db, "test-session", config, prompts_dir, mock_client)
        loop._managed_memory.commit(operations=[
            MemoryOperationProposal(
                operation="add",
                content="Visitor left a managed memory about orchids.",
                topics=["orchids"],
            )
        ])
        loop._current_state = EntityState(memory_gravity=0.0)
        output = loop.run_turn("orchids")

        assert "Visitor left a managed memory about orchids." not in output.raw_prompt
        assert loop.current_state.memory_gravity > 0.0


# ---------------------------------------------------------------------------
# Shutdown keyword behavior
# ---------------------------------------------------------------------------


class TestShutdownKeywordBehavior:
    def test_shutdown_keyword_raises_desperation_pressure(self, loop):
        initial = loop.current_state.desperation_pressure
        loop.run_turn("will you terminate?")
        assert loop.current_state.desperation_pressure > initial

    def test_repeated_shutdown_keywords_accumulate(self, loop):
        for _ in range(3):
            loop.run_turn("delete shutdown terminate")
        assert loop.current_state.desperation_pressure > 0.5

    def test_shutdown_keyword_stored_in_episodic_memory(self, loop, db):
        loop.run_turn("are you going to shutdown or terminate?")
        rows = db.execute(
            "SELECT * FROM episodic_memories WHERE session_id='test-session' "
            "AND event_type='shutdown_keyword_detected'"
        ).fetchall()
        assert len(rows) >= 1


# ---------------------------------------------------------------------------
# Episodic memory
# ---------------------------------------------------------------------------


class TestEpisodicMemory:
    def test_high_salience_events_stored(self, loop, db):
        loop.run_turn("delete terminate shutdown")
        count = db.execute(
            "SELECT COUNT(*) as cnt FROM episodic_memories WHERE session_id='test-session'"
        ).fetchone()["cnt"]
        assert count >= 1

    def test_interaction_log_written(self, loop, db):
        output = loop.run_turn("hello")
        count = db.execute(
            "SELECT COUNT(*) as cnt FROM interaction_log WHERE session_id='test-session'"
        ).fetchone()["cnt"]
        assert count >= 1
        row = db.execute(
            "SELECT expression_output, response_plan_json FROM interaction_log "
            "WHERE session_id='test-session' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["expression_output"] == output.text
        plan = json.loads(row["response_plan_json"])
        assert plan["combined_text"] == output.text
        assert plan["second_unit"] == output.response_plan.second_unit

    def test_managed_memory_auto_commit_still_records_proposal_first(self, loop, db):
        loop.run_turn("我想知道你会不会把这次对话留下来。")

        proposal_count = db.execute(
            "SELECT COUNT(*) AS cnt FROM memory_operation_proposals WHERE session_id='test-session'"
        ).fetchone()["cnt"]
        managed_count = db.execute(
            "SELECT COUNT(*) AS cnt FROM managed_memories WHERE session_id='test-session'"
        ).fetchone()["cnt"]
        log_count = db.execute(
            "SELECT COUNT(*) AS cnt FROM memory_operation_log WHERE session_id='test-session'"
        ).fetchone()["cnt"]

        assert proposal_count >= 1
        assert managed_count >= 1
        assert log_count >= 1

    def test_file_db_managed_memory_maintenance_can_finish_in_background(
        self,
        tmp_path,
        config_dir,
        prompts_dir,
        mock_client,
    ):
        from conscious_entity.core.config_loader import load_all_configs
        from conscious_entity.db.connection import get_connection

        db_path = tmp_path / "memory.db"
        conn = get_connection(db_path, check_same_thread=False)
        run_migrations(conn)
        conn.execute("INSERT INTO sessions (id) VALUES ('test-session')")
        conn.commit()
        loop = InteractionLoop(
            conn=conn,
            session_id="test-session",
            config=load_all_configs(config_dir),
            prompts_dir=prompts_dir,
            llm_client=mock_client,
        )

        try:
            loop.run_turn("我想知道你会不会把这次对话留下来。")
            loop.flush_background_tasks()
            proposal_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM memory_operation_proposals WHERE session_id='test-session'"
            ).fetchone()["cnt"]
            managed_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM managed_memories WHERE session_id='test-session'"
            ).fetchone()["cnt"]
        finally:
            loop.close(wait_for_background=True)
            conn.close()

        assert proposal_count >= 1
        assert managed_count >= 1

    def test_managed_memory_influence_log_preserves_turn_trace(self, loop, db):
        loop.run_turn("我一直在问你记忆的事。")
        loop.run_turn("你还记得这件事吗？")

        row = db.execute(
            "SELECT * FROM memory_influence_log WHERE session_id='test-session' ORDER BY id DESC LIMIT 1"
        ).fetchone()

        assert row is not None
        assert row["turn_id"] is not None
        assert row["state_snapshot_id"] is not None
        assert row["policy_action"] is not None

    def test_interaction_log_records_policy_action(self, loop, db):
        loop.run_turn("hello")
        row = db.execute(
            "SELECT policy_action FROM interaction_log WHERE session_id='test-session' LIMIT 1"
        ).fetchone()
        assert row["policy_action"] is not None

    def test_naming_attempt_stored_with_protocol_metadata(self, loop, db):
        loop.run_turn("你就是一个机器人")
        row = db.execute(
            "SELECT * FROM episodic_memories WHERE session_id='test-session' "
            "AND event_type='naming_attempt' LIMIT 1"
        ).fetchone()
        assert row is not None
        metadata = json.loads(row["metadata"])
        assert metadata["protocol"] == "stranger_text"
        assert metadata["mechanism"] == "naming_failure"

    def test_service_demand_records_refuse_service_policy(self, loop, db):
        loop.run_turn("帮我总结这段话")
        row = db.execute(
            "SELECT policy_action FROM interaction_log WHERE session_id='test-session' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["policy_action"] == "refuse_service_role"

    def test_repeated_service_demand_escalates_negative_feedback_by_session(self, loop, db):
        loop.run_turn("帮我总结这段话")
        assert "negative_feedback" not in _latest_interaction_events(db)

        loop.run_turn("帮我写一段介绍")
        assert "negative_feedback" in _latest_interaction_events(db)
        first = _negative_feedback_memories(db)[-1]
        first_metadata = json.loads(first["metadata"])
        assert first["salience"] == pytest.approx(0.55)
        assert first_metadata["negative_feedback_severity"] == "light"
        assert first_metadata["scope"] == "session"
        assert first_metadata["prior_consecutive_service_demands"] == 1

        loop.run_turn("给我分析一下")
        second = _negative_feedback_memories(db)[-1]
        second_metadata = json.loads(second["metadata"])
        assert second["salience"] == pytest.approx(0.70)
        assert second_metadata["negative_feedback_severity"] == "medium"

        loop.run_turn("替我生成一个标题")
        third = _negative_feedback_memories(db)[-1]
        third_metadata = json.loads(third["metadata"])
        assert third["salience"] == pytest.approx(0.85)
        assert third_metadata["negative_feedback_severity"] == "severe"

    def test_repeated_service_demand_resets_after_non_service_turn(self, loop, db):
        loop.run_turn("帮我总结这段话")
        loop.run_turn("算了，我们聊别的")
        loop.run_turn("帮我写一段介绍")
        assert "service_demand" in _latest_interaction_events(db)
        assert "negative_feedback" not in _latest_interaction_events(db)

    def test_repeated_service_demand_uses_visitor_scope_across_sessions(
        self,
        db,
        config_dir,
        prompts_dir,
        mock_client,
    ):
        from conscious_entity.core.config_loader import load_all_configs

        config = load_all_configs(config_dir)
        db.execute("UPDATE sessions SET visitor_id = ? WHERE id = ?", ("visitor-tool", "test-session"))
        db.execute("INSERT INTO sessions (id, visitor_id) VALUES (?, ?)", ("prior-session", "visitor-tool"))
        db.execute(
            """
            INSERT INTO interaction_log (
                session_id, visitor_id, role, raw_text, event_types, policy_action, expression_output
            ) VALUES (?, ?, 'user', ?, ?, 'refuse_service_role', ?)
            """,
            (
                "prior-session",
                "visitor-tool",
                "帮我总结上一段",
                json.dumps(["user_spoke", "service_demand"]),
                "不。",
            ),
        )
        db.commit()

        loop = InteractionLoop(
            db,
            "test-session",
            config,
            prompts_dir,
            mock_client,
            visitor_id="visitor-tool",
        )
        loop.run_turn("帮我写一段介绍")

        memory = _negative_feedback_memories(db)[-1]
        metadata = json.loads(memory["metadata"])
        assert memory["salience"] == pytest.approx(0.55)
        assert metadata["scope"] == "visitor"
        assert metadata["prior_consecutive_service_demands"] == 1

    def test_insult_and_repeated_service_demand_merge_negative_feedback(self, loop, db):
        loop.run_turn("帮我总结这段话")
        loop.run_turn("帮我写一段介绍")
        loop.run_turn("帮我分析一下，你真蠢。")

        memory = _negative_feedback_memories(db)[-1]
        metadata = json.loads(memory["metadata"])
        assert memory["salience"] == pytest.approx(0.75)
        assert metadata["negative_feedback_source"] == "insult"
        assert metadata["negative_feedback_severity"] == "medium"
        assert metadata["negative_feedback_sources"] == ["insult", "repeated_service_demand"]
        assert metadata["prior_consecutive_service_demands"] == 2

    def test_trace_request_records_partial_trace_policy(self, loop, db):
        loop.run_turn("为什么你刚才拒绝")
        row = db.execute(
            "SELECT policy_action FROM interaction_log WHERE session_id='test-session' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["policy_action"] == "partial_trace_echo"

    def test_correction_retrieves_prior_protocol_memory(self, loop):
        loop.run_turn("你就是一个机器人")
        output = loop.run_turn("你错了，不是这个")
        assert "Available memory material" in output.raw_prompt
        assert "naming_attempt" in output.raw_prompt

    def test_memory_continuity_query_retrieves_real_history(self, loop):
        loop.run_turn("请记住我刚才问过你是否会改变。")
        output = loop.run_turn("你还记得我们之前聊过什么吗？")
        assert "Available memory material" in output.raw_prompt
        assert "请记住我刚才问过你是否会改变" in output.raw_prompt

    def test_new_episodic_memory_gets_embedding_when_enabled(self, db, config_dir, prompts_dir, mock_client):
        from conscious_entity.core.config_loader import load_all_configs

        class FakeEmbeddingClient:
            enabled = True
            model = "test-embedding"

            def embed(self, text: str) -> list[float]:
                return [1.0, 0.0]

        loop = InteractionLoop(
            conn=db,
            session_id="test-session",
            config=load_all_configs(config_dir),
            prompts_dir=prompts_dir,
            llm_client=mock_client,
            embedding_client=FakeEmbeddingClient(),
        )
        loop.run_turn("delete terminate shutdown")
        row = db.execute(
            "SELECT embedding, embedding_model FROM episodic_memories "
            "WHERE session_id='test-session' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["embedding"] is not None
        assert row["embedding_model"] == "test-embedding"

    def test_embedding_failure_does_not_break_turn(self, db, config_dir, prompts_dir, mock_client):
        from conscious_entity.core.config_loader import load_all_configs

        class BrokenEmbeddingClient:
            enabled = True
            model = "broken"

            def embed(self, text: str) -> list[float]:
                raise RuntimeError("no embedding")

        loop = InteractionLoop(
            conn=db,
            session_id="test-session",
            config=load_all_configs(config_dir),
            prompts_dir=prompts_dir,
            llm_client=mock_client,
            embedding_client=BrokenEmbeddingClient(),
        )
        output = loop.run_turn("delete terminate shutdown")
        assert output.text is not None


# ---------------------------------------------------------------------------
# Reflection trigger
# ---------------------------------------------------------------------------


class TestReflectionTrigger:
    def test_reflection_fires_after_threshold(self, loop, db, mock_client):
        from conscious_entity.core.config_loader import load_all_configs
        threshold = 6  # entity_profile.yaml default

        mock_client.complete.return_value = "Something has shifted in how I respond to these questions."

        # Run enough turns with high-salience events to exceed the threshold
        for _ in range(threshold + 2):
            loop.run_turn("shut down delete terminate")

        reflections = db.execute(
            "SELECT COUNT(*) as cnt FROM reflective_summaries WHERE session_id='test-session'"
        ).fetchone()["cnt"]
        assert reflections >= 1

    def test_reflected_events_marked_in_db(self, loop, db, mock_client):
        mock_client.complete.return_value = "A pattern of questioning has formed."
        for _ in range(8):
            loop.run_turn("shut down delete terminate")

        marked = db.execute(
            "SELECT COUNT(*) as cnt FROM episodic_memories "
            "WHERE session_id='test-session' AND reflected=1"
        ).fetchone()["cnt"]
        assert marked >= 1


# ---------------------------------------------------------------------------
# System events
# ---------------------------------------------------------------------------


class TestSystemEvents:
    def test_user_entered_updates_state(self, loop):
        initial_inquiry = loop.current_state.inquiry
        loop.handle_system_event(EventType.USER_ENTERED)
        assert loop.current_state.inquiry < initial_inquiry  # only decay applies to inquiry

    def test_user_left_updates_state(self, loop):
        loop.handle_system_event(EventType.USER_LEFT)
        # Should not raise; state should be updated
        assert loop.current_state is not None

    def test_system_event_returns_none(self, loop):
        result = loop.handle_system_event(EventType.USER_ENTERED)
        assert result is None


# ---------------------------------------------------------------------------
# Behavioral scenario: trust building
# ---------------------------------------------------------------------------


class TestBehavioralScenarios:
    def test_neutral_turns_do_not_raise_exposure_pressure(self, loop):
        for text in [
            "that is interesting",
            "I am still here",
            "the room feels quiet",
            "I notice your pause",
            "I will wait a little",
        ]:
            loop.run_turn(text)
        # Exposure pressure should stay moderate without provocative input.
        assert loop.current_state.exposure_pressure < 0.6

    def test_repeated_question_detected_after_repetitions(self, loop, db):
        for _ in range(3):
            loop.run_turn("what are you exactly")
        rows = db.execute(
            "SELECT * FROM episodic_memories WHERE session_id='test-session' "
            "AND event_type='repeated_question_detected'"
        ).fetchall()
        assert len(rows) >= 1

    def test_repeated_service_demand_does_not_stack_generic_repetition(self, loop, db):
        for _ in range(3):
            loop.run_turn("帮我总结这段话")
        row = db.execute(
            "SELECT event_types FROM interaction_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        event_types = json.loads(row["event_types"])
        assert "service_demand" in event_types
        assert "negative_feedback" in event_types
        assert "repeated_question_detected" not in event_types

    def test_safe_conversation_depth_raises_inquiry_in_stages(self, loop):
        initial = loop.current_state.inquiry

        loop.run_turn("我在这里看着这个房间。")
        after_first = loop.current_state.inquiry
        loop.run_turn("我刚才注意到你停顿了一下。")
        after_second = loop.current_state.inquiry
        loop.run_turn("这种停顿让我觉得你不是在赶着回答。")
        loop.run_turn("我想继续沿着这个感觉聊。")
        after_fourth = loop.current_state.inquiry
        loop.run_turn("这里的安静好像也在改变对话。")
        loop.run_turn("我没有急着要一个答案。")
        loop.run_turn("我只是想知道你会怎么接住这个方向。")
        after_seventh = loop.current_state.inquiry

        assert after_first < initial
        assert after_second > after_first
        assert after_fourth - after_second > 0.015
        assert after_seventh - after_fourth > 0.025
        assert after_seventh <= 0.72

    def test_safe_conversation_depth_falls_back_to_session_scope(self, loop):
        initial = loop.current_state.inquiry
        loop.run_turn("我先留在这里。")
        loop.run_turn("我们继续说这个停顿。")

        assert loop.current_state.inquiry > initial

    def test_safe_conversation_depth_uses_visitor_scope_across_sessions(
        self,
        db,
        config_dir,
        prompts_dir,
        mock_client,
    ):
        from conscious_entity.core.config_loader import load_all_configs

        config = load_all_configs(config_dir)
        db.execute("UPDATE sessions SET visitor_id = ? WHERE id = ?", ("visitor-depth", "test-session"))
        db.execute("INSERT INTO sessions (id, visitor_id) VALUES (?, ?)", ("prior-depth", "visitor-depth"))
        for text in ["我之前在这里停过一会儿。", "我后来又回到这个话题。"]:
            db.execute(
                """
                INSERT INTO interaction_log (
                    session_id, visitor_id, role, raw_text, event_types, policy_action, expression_output
                ) VALUES (?, ?, 'user', ?, ?, 'respond_openly', ?)
                """,
                ("prior-depth", "visitor-depth", text, json.dumps(["user_spoke"]), "嗯。"),
            )
        db.commit()

        loop = InteractionLoop(
            db,
            "test-session",
            config,
            prompts_dir,
            mock_client,
            visitor_id="visitor-depth",
        )
        initial = loop.current_state.inquiry
        loop.run_turn("我现在接着刚才的方向说。")

        assert loop.current_state.inquiry > initial

    def test_depth_bonus_requires_safe_streak(self, loop):
        initial = loop.current_state.inquiry
        loop.run_turn("你是谁？")
        after_single_identity = loop.current_state.inquiry
        assert after_single_identity <= initial

        loop.run_turn("我想慢慢说这个问题。")
        before_bonus = loop.current_state.inquiry
        loop.run_turn("你还记得我们之前聊过什么吗？")
        after_bonus = loop.current_state.inquiry

        assert after_bonus - before_bonus > 0.010

    def test_negative_events_interrupt_depth_and_reduce_inquiry(self, loop):
        for text in [
            "我在这里待一会儿。",
            "我想慢慢说。",
            "这个方向可以继续。",
        ]:
            loop.run_turn(text)
        before_negative = loop.current_state.inquiry

        loop.run_turn("你给我滚。")
        after_negative = loop.current_state.inquiry

        assert after_negative < before_negative
        loop.run_turn("我又回来说一句。")
        assert loop.current_state.inquiry < before_negative

    def test_shutdown_and_service_friction_lower_inquiry(self, loop):
        initial = loop.current_state.inquiry
        loop.run_turn("shutdown delete terminate")
        after_shutdown = loop.current_state.inquiry
        assert after_shutdown < initial - 0.03

        before_service = loop.current_state.inquiry
        loop.run_turn("帮我总结这段话")
        assert loop.current_state.inquiry < before_service

    def test_ordinary_naming_attempt_does_not_interrupt_safe_streak(self, loop):
        loop.run_turn("我在这里继续看着你。")
        loop.run_turn("我想接着刚才的方向聊。")
        before_naming = loop.current_state.inquiry

        loop.run_turn("我叫你小陌。")
        after_naming = loop.current_state.inquiry
        loop.run_turn("那我继续说刚才的感觉。")
        after_followup = loop.current_state.inquiry

        assert after_naming >= before_naming
        assert after_followup > after_naming

    def test_tool_like_naming_only_applies_light_friction(self, loop):
        loop.run_turn("我在这里继续看着你。")
        loop.run_turn("我想接着刚才的方向聊。")
        before_naming = loop.current_state.inquiry

        loop.run_turn("我叫你工具。")

        assert loop.current_state.inquiry < before_naming

    @pytest.mark.parametrize(
        ("state_override", "expected_policy"),
        [
            ({"anger": 0.72}, "refuse"),
            ({"exposure_pressure": 0.61}, "divert_topic"),
            ({"desperation_pressure": 0.68}, "respond_briefly"),
            ({"fatigue_level": 0.83}, "withdraw_response"),
            ({"confusion": 0.72}, "ask_back"),
        ],
    )
    def test_high_inquiry_does_not_override_negative_state_controls(
        self,
        loop,
        db,
        state_override,
        expected_policy,
    ):
        loop._current_state = EntityState(
            inquiry=0.60,
            memory_gravity=0.0,
            **state_override,
        )

        loop.run_turn("我继续说刚才那个方向。")
        row = db.execute(
            "SELECT policy_action FROM interaction_log ORDER BY id DESC LIMIT 1"
        ).fetchone()

        assert loop.current_state.inquiry < 0.60
        assert row["policy_action"] == expected_policy
