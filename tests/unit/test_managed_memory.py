from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from conscious_entity.db.migrations import run_migrations
from conscious_entity.llm.claude_client import ClaudeClient
from conscious_entity.memory.managed import LocalManagedMemoryProvider, MemoryProviderConfig
from conscious_entity.memory.models import MemoryOperationProposal


@pytest.fixture
def conn():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    run_migrations(db)
    db.execute("INSERT INTO sessions (id, session_type) VALUES (?, ?)", ("test-session", "test"))
    db.commit()
    yield db
    db.close()


@pytest.fixture
def prompts_dir() -> Path:
    return Path(__file__).parent.parent.parent / "prompts"


def _provider(conn, prompts_dir, *, auto_commit=True, llm_output=""):
    client = MagicMock(spec=ClaudeClient)
    client.complete.return_value = llm_output
    return LocalManagedMemoryProvider(
        conn,
        "test-session",
        llm_client=client,
        prompts_dir=prompts_dir,
        config=MemoryProviderConfig(auto_commit=auto_commit),
    )


def test_propose_writes_proposal_but_not_managed_memory(conn, prompts_dir):
    provider = _provider(conn, prompts_dir)

    proposals = provider.propose(
        [{"role": "user", "content": "我刚才一直在测试你会不会记得我。"}],
        {"source_turn_ids": [1]},
    )

    assert len(proposals) == 1
    assert proposals[0].status == "pending"
    assert conn.execute("SELECT COUNT(*) AS cnt FROM memory_operation_proposals").fetchone()["cnt"] == 1
    assert conn.execute("SELECT COUNT(*) AS cnt FROM managed_memories").fetchone()["cnt"] == 0


def test_commit_add_creates_managed_memory_and_operation_log(conn, prompts_dir):
    provider = _provider(conn, prompts_dir)
    proposal = provider.propose(
        [{"role": "user", "content": "我反复问你会不会被关掉。"}],
        {"source_turn_ids": [3]},
    )[0]

    committed = provider.commit(proposal_ids=[proposal.id])

    assert committed[0]["operation"] == "add"
    memory = conn.execute("SELECT * FROM managed_memories").fetchone()
    assert memory is not None
    assert memory["status"] == "active"
    assert "关" in memory["content"]
    assert conn.execute("SELECT COUNT(*) AS cnt FROM memory_operation_log").fetchone()["cnt"] == 1


def test_search_returns_explainable_active_managed_memories(conn, prompts_dir):
    provider = _provider(conn, prompts_dir)
    provider.commit(operations=[
        MemoryOperationProposal(
            operation="add",
            content="Visitor repeatedly asked whether Stranger would be shut down.",
            topics=["shutdown"],
            confidence=0.8,
            source_turn_ids=[1],
        )
    ])

    results = provider.search("shutdown", explain=True)

    assert len(results) == 1
    assert results[0].memory_type == "managed"
    assert results[0].metadata["explanation"]
    assert results[0].metadata["source_turn_ids"] == [1]


def test_preview_influence_does_not_write(conn, prompts_dir):
    provider = _provider(conn, prompts_dir)
    provider.commit(operations=[
        MemoryOperationProposal(operation="add", content="Visitor returned to naming pressure.", topics=["naming"])
    ])
    before = conn.execute("SELECT COUNT(*) AS cnt FROM memory_influence_log").fetchone()["cnt"]

    preview = provider.preview_influence("naming", {})
    after = conn.execute("SELECT COUNT(*) AS cnt FROM memory_influence_log").fetchone()["cnt"]

    assert preview["explanation"]["writes"] is False
    assert after == before
    deltas = preview["state_influence"]["deltas"]
    assert deltas["memory_gravity"] > 0
    assert "inquiry" not in deltas
    assert deltas["positive_opening"] > 0
    assert "happiness" not in deltas
    assert preview["results"]
    assert preview["expression_context"] == []
    assert preview["policy_influence"]["suggested_action"] is None
    assert preview["explanation"]["memory_gravity_gate"]["passed"] is False


def test_preview_influence_allows_memory_context_when_memory_gravity_gate_passes(conn, prompts_dir):
    provider = _provider(conn, prompts_dir)
    provider.commit(operations=[
        MemoryOperationProposal(operation="add", content="Visitor returned to naming pressure.", topics=["naming"])
    ])

    preview = provider.preview_influence("naming", {"state": {"memory_gravity": 0.24}})

    assert preview["expression_context"]
    assert preview["policy_influence"]["suggested_action"] == "retrieve_selective_memory"
    assert preview["policy_influence"]["memory_gravity_gate_passed"] is True
    assert preview["explanation"]["memory_gravity_gate"]["effective"] >= 0.25


def test_explicit_memory_event_bypasses_memory_gravity_gate(conn, prompts_dir):
    provider = _provider(conn, prompts_dir)
    provider.commit(operations=[
        MemoryOperationProposal(operation="add", content="Visitor asked about memory continuity.", topics=["memory"])
    ])

    preview = provider.preview_influence(
        "memory",
        {"events": ["memory_continuity_query"], "state": {"memory_gravity": 0.0}},
    )

    assert preview["expression_context"]
    assert preview["policy_influence"]["suggested_action"] == "retrieve_selective_memory"
    assert preview["explanation"]["memory_gravity_gate"]["explicit_memory_event"] is True


def test_archive_hides_memory_and_restore_reactivates(conn, prompts_dir):
    provider = _provider(conn, prompts_dir)
    memory_id = provider.commit(operations=[
        MemoryOperationProposal(operation="add", content="Visitor asked about memory continuity.", topics=["memory"])
    ])[0]["memory_id"]

    provider.archive(memory_id)
    assert provider.search("memory") == []

    provider.restore(memory_id)
    assert provider.search("memory")
