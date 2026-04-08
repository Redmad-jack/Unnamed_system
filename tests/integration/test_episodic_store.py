from __future__ import annotations

import pytest

from conscious_entity.memory.episodic_store import EpisodicStore
from conscious_entity.memory.models import EpisodicMemory, ReflectiveSummary
from conscious_entity.memory.reflective_store import ReflectiveStore
from conscious_entity.state.state_core import EntityState

SESSION = "test-session-001"


def make_session(db):
    db.execute(
        "INSERT INTO sessions (id) VALUES (?)",
        (SESSION,),
    )
    db.commit()


def make_episodic(content: str = "something happened", salience: float = 0.6) -> EpisodicMemory:
    return EpisodicMemory(
        session_id=SESSION,
        event_type="user_spoke",
        content=content,
        salience=salience,
    )


def make_reflective(content: str = "a pattern emerged") -> ReflectiveSummary:
    return ReflectiveSummary(
        session_id=SESSION,
        content=content,
        source_event_ids=[1, 2],
        state_at_reflection=EntityState(),
    )


# ─── EpisodicStore ───────────────────────────────────────────────────────────

@pytest.fixture
def episodic(in_memory_db):
    make_session(in_memory_db)
    return EpisodicStore(in_memory_db, SESSION)


def test_store_and_get_recent(episodic):
    episodic.store(make_episodic("first"))
    episodic.store(make_episodic("second"))
    episodic.store(make_episodic("third"))
    results = episodic.get_recent()
    contents = [r.content for r in results]
    assert "first" in contents and "second" in contents and "third" in contents


def test_get_recent_returns_newest_first(episodic):
    episodic.store(make_episodic("older"))
    episodic.store(make_episodic("newer"))
    results = episodic.get_recent()
    assert results[0].content == "newer"


def test_get_recent_limit(episodic):
    for i in range(5):
        episodic.store(make_episodic(f"event {i}"))
    results = episodic.get_recent(limit=2)
    assert len(results) == 2


def test_get_unreflected_returns_pending(episodic):
    id1 = episodic.store(make_episodic("event A"))
    id2 = episodic.store(make_episodic("event B"))
    # Manually insert a reflection to mark against
    cursor = episodic._conn.execute(
        """
        INSERT INTO reflective_summaries
            (session_id, content, source_event_ids, state_at_reflection)
        VALUES (?, ?, ?, ?)
        """,
        (SESSION, "summary", "[1]", "{}"),
    )
    episodic._conn.commit()
    reflection_id = cursor.lastrowid
    episodic.mark_reflected(id1, reflection_id)
    unreflected = episodic.get_unreflected()
    ids = [m.id for m in unreflected]
    assert id1 not in ids
    assert id2 in ids


def test_mark_reflected_updates_flag(episodic):
    event_id = episodic.store(make_episodic("test event"))
    cursor = episodic._conn.execute(
        """
        INSERT INTO reflective_summaries
            (session_id, content, source_event_ids, state_at_reflection)
        VALUES (?, ?, ?, ?)
        """,
        (SESSION, "summary", "[]", "{}"),
    )
    episodic._conn.commit()
    reflection_id = cursor.lastrowid
    episodic.mark_reflected(event_id, reflection_id)
    row = episodic._conn.execute(
        "SELECT reflected, reflection_id FROM episodic_memories WHERE id = ?",
        (event_id,),
    ).fetchone()
    assert row["reflected"] == 1
    assert row["reflection_id"] == reflection_id


def test_get_recent_empty(episodic):
    assert episodic.get_recent() == []


def test_episodic_memory_fields_persisted(episodic):
    mem = EpisodicMemory(
        session_id=SESSION,
        event_type="shutdown_keyword_detected",
        content="will you be turned off",
        salience=0.9,
        raw_text="will you be turned off",
        metadata={"keyword": "turned off"},
    )
    row_id = episodic.store(mem)
    results = episodic.get_recent(limit=1)
    assert results[0].id == row_id
    assert results[0].event_type == "shutdown_keyword_detected"
    assert results[0].salience == pytest.approx(0.9)
    assert results[0].metadata == {"keyword": "turned off"}


# ─── ReflectiveStore ──────────────────────────────────────────────────────────

@pytest.fixture
def reflective(in_memory_db):
    make_session(in_memory_db)
    return ReflectiveStore(in_memory_db, SESSION)


def test_reflective_store_and_get_all(reflective):
    row_id = reflective.store(make_reflective("insight one"))
    results = reflective.get_all()
    assert len(results) == 1
    assert results[0].id == row_id
    assert results[0].content == "insight one"
    assert results[0].active is True


def test_reflective_get_all_active_only(reflective):
    id1 = reflective.store(make_reflective("active insight"))
    id2 = reflective.store(make_reflective("superseded insight"))
    reflective.mark_superseded(id2)
    active = reflective.get_all(active_only=True)
    ids = [s.id for s in active]
    assert id1 in ids
    assert id2 not in ids


def test_reflective_get_all_includes_inactive(reflective):
    id1 = reflective.store(make_reflective("active"))
    id2 = reflective.store(make_reflective("superseded"))
    reflective.mark_superseded(id2)
    all_summaries = reflective.get_all(active_only=False)
    ids = [s.id for s in all_summaries]
    assert id1 in ids
    assert id2 in ids


def test_reflective_state_roundtrip(reflective):
    state = EntityState(resistance=0.75, curiosity=0.3)
    summary = ReflectiveSummary(
        session_id=SESSION,
        content="state test",
        source_event_ids=[10, 11, 12],
        state_at_reflection=state,
    )
    reflective.store(summary)
    result = reflective.get_all()[0]
    assert result.state_at_reflection.resistance == pytest.approx(0.75)
    assert result.source_event_ids == [10, 11, 12]
