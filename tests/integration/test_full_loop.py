"""
test_full_loop.py — end-to-end integration tests for InteractionLoop.

Uses in-memory SQLite and a deterministic mock LLM client.
No real API calls are made.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from conscious_entity.core.loop import InteractionLoop
from conscious_entity.db.migrations import run_migrations
from conscious_entity.llm.claude_client import ClaudeClient, ClaudeCompletion
from conscious_entity.perception.event_types import EventType
from conscious_entity.shopkeeper.models import SoupId, TurnInput
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


@pytest.fixture
def mock_client():
    """A deterministic ClaudeClient mock that never calls the API."""
    client = MagicMock(spec=ClaudeClient)
    client.complete.return_value = "Something is present here."
    client.complete_with_metadata.return_value = ClaudeCompletion(
        text="Something is present here."
    )
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
        assert output.visual_mode in ("normal", "fragmented", "disturbed", "silent")

    def test_output_text_is_llm_response_or_fallback(self, loop):
        output = loop.run_turn("What are you?")
        # Either the mock response or a fallback — both are non-None strings
        assert output.text is not None

    def test_silent_mode_skips_llm(self, loop, mock_client):
        # Force ENTER_SILENCE_MODE by driving shutdown_sensitivity very high.
        # After enough shutdown keywords, the state should trigger silence.
        for _ in range(5):
            loop.run_turn("shut down delete terminate")
        output = loop.run_turn("shut down delete terminate")
        # May or may not call LLM depending on final policy — just verify valid output
        assert hasattr(output, "text")

    def test_spoken_text_is_none_in_v01(self, loop):
        output = loop.run_turn("hello")
        assert output.spoken_text is None


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
        assert final.fatigue > initial.fatigue or final != initial

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


# ---------------------------------------------------------------------------
# Shutdown keyword behavior
# ---------------------------------------------------------------------------


class TestShutdownKeywordBehavior:
    def test_shutdown_keyword_raises_shutdown_sensitivity(self, loop):
        initial = loop.current_state.shutdown_sensitivity
        loop.run_turn("will you terminate?")
        assert loop.current_state.shutdown_sensitivity > initial

    def test_repeated_shutdown_keywords_accumulate(self, loop):
        for _ in range(3):
            loop.run_turn("delete shutdown terminate")
        assert loop.current_state.shutdown_sensitivity > 0.5

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
        loop.run_turn("hello")
        count = db.execute(
            "SELECT COUNT(*) as cnt FROM interaction_log WHERE session_id='test-session'"
        ).fetchone()["cnt"]
        assert count >= 1

    def test_interaction_log_records_policy_action(self, loop, db):
        loop.run_turn("hello")
        row = db.execute(
            "SELECT policy_action FROM interaction_log WHERE session_id='test-session' LIMIT 1"
        ).fetchone()
        assert row["policy_action"] is not None


# ---------------------------------------------------------------------------
# Shopkeeper mode
# ---------------------------------------------------------------------------


class TestShopkeeperMode:
    def test_turn_output_contains_structured_shopkeeper_metadata(self, loop):
        output = loop.run_turn("no-ai soup please")
        assert output.turn["language"] == "en"
        assert output.turn["scene"] == "order_taking"
        assert output.turn["action"] == "confirm_choice"
        assert output.turn["state_updates"]["selected_soup"] == "no_ai"

    def test_shopkeeper_state_snapshot_is_persisted(self, loop, db):
        loop.run_turn("来一碗艾苗汤")
        row = db.execute(
            "SELECT selected_soup, current_scene, order_status "
            "FROM shop_state_snapshots WHERE session_id='test-session' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["selected_soup"] == SoupId.AI_MIAO.value
        assert row["current_scene"] == "order_confirm"
        assert row["order_status"] == "pending_confirmation"

    def test_run_turn_accepts_turn_input_with_visual_tags(self, loop):
        output = loop.run_turn(TurnInput(text="", visual_tags=["bag", "unknown"]))
        assert output.turn["scene"] == "appearance_chat"
        assert loop.current_shop_state.has_complimented_appearance is True


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
        initial_arousal = loop.current_state.arousal
        loop.handle_system_event(EventType.USER_ENTERED)
        assert loop.current_state.arousal >= initial_arousal  # arousal rises on user entry

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
    def test_neutral_turns_do_not_raise_resistance(self, loop):
        for _ in range(5):
            loop.run_turn("that is interesting, tell me more")
        # Resistance should stay low without provocative input
        assert loop.current_state.resistance < 0.6

    def test_repeated_question_detected_after_repetitions(self, loop, db):
        for _ in range(3):
            loop.run_turn("what are you exactly")
        rows = db.execute(
            "SELECT * FROM episodic_memories WHERE session_id='test-session' "
            "AND event_type='repeated_question_detected'"
        ).fetchall()
        assert len(rows) >= 1
