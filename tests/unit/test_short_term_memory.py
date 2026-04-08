from __future__ import annotations

from datetime import datetime

from conscious_entity.memory.models import ShortTermEntry
from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.perception.event_types import EventType


def make_entry(role: str, content: str, event_type=None) -> ShortTermEntry:
    return ShortTermEntry(role=role, content=content, timestamp=datetime.now(), event_type=event_type)


# --- add / get_recent ---

def test_add_and_get_recent_order():
    mem = ShortTermMemory()
    mem.add(make_entry("user", "first"))
    mem.add(make_entry("entity", "second"))
    mem.add(make_entry("user", "third"))
    result = mem.get_recent(3)
    assert [e.content for e in result] == ["first", "second", "third"]


def test_get_recent_respects_n_limit():
    mem = ShortTermMemory()
    for i in range(5):
        mem.add(make_entry("user", f"msg {i}"))
    result = mem.get_recent(2)
    assert len(result) == 2
    assert result[-1].content == "msg 4"


def test_get_recent_fewer_than_n_returns_all():
    mem = ShortTermMemory()
    mem.add(make_entry("user", "only one"))
    result = mem.get_recent(5)
    assert len(result) == 1


def test_get_recent_empty_returns_empty():
    mem = ShortTermMemory()
    assert mem.get_recent() == []


# --- max_turns eviction ---

def test_max_turns_eviction():
    mem = ShortTermMemory(max_turns=3)
    for i in range(4):
        mem.add(make_entry("user", f"msg {i}"))
    result = mem.get_recent(10)
    contents = [e.content for e in result]
    assert "msg 0" not in contents
    assert contents == ["msg 1", "msg 2", "msg 3"]


# --- count_repetitions ---

def test_count_repetitions_no_match():
    mem = ShortTermMemory()
    mem.add(make_entry("user", "the weather is nice"))
    assert mem.count_repetitions("completely different topic here") == 0


def test_count_repetitions_exact_match():
    mem = ShortTermMemory()
    mem.add(make_entry("user", "will you be shut down"))
    mem.add(make_entry("user", "will you be shut down"))
    assert mem.count_repetitions("will you be shut down") == 2


def test_count_repetitions_partial_overlap():
    mem = ShortTermMemory()
    mem.add(make_entry("user", "shut down the system"))
    # "shut down" appears in both → 2/4 overlap = 0.5 → counts
    assert mem.count_repetitions("shut down") >= 1


def test_count_repetitions_only_counts_user_role():
    mem = ShortTermMemory()
    mem.add(make_entry("entity", "will you be shut down"))
    mem.add(make_entry("user", "will you be shut down"))
    # entity role should not count
    assert mem.count_repetitions("will you be shut down") == 1


def test_count_repetitions_empty_memory():
    mem = ShortTermMemory()
    assert mem.count_repetitions("anything") == 0


def test_count_repetitions_empty_text():
    mem = ShortTermMemory()
    mem.add(make_entry("user", "some text"))
    assert mem.count_repetitions("") == 0
