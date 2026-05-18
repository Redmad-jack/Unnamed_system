from __future__ import annotations

import json

from conscious_entity.memory.retrieval import MemoryRetriever
from conscious_entity.memory.vector import cosine_similarity, decode_embedding, encode_embedding
from conscious_entity.state.state_core import EntityState


def _session(conn, session_id: str, session_type: str = "test") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO sessions (id, session_type) VALUES (?, ?)",
        (session_id, session_type),
    )
    conn.commit()


def _visitor(conn, visitor_id: str, display_name: str = "Visitor") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO visitor_profiles (id, display_name) VALUES (?, ?)",
        (visitor_id, display_name),
    )
    conn.commit()


def _assign_visitor(conn, session_id: str, visitor_id: str) -> None:
    conn.execute(
        "UPDATE sessions SET visitor_id = ? WHERE id = ?",
        (visitor_id, session_id),
    )
    conn.commit()


def _interaction(
    conn,
    session_id: str,
    user_text: str,
    entity_text: str,
    *,
    response_plan: dict | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO interaction_log (
            session_id, role, raw_text, event_types, policy_action,
            expression_output, response_plan_json
        ) VALUES (?, 'user', ?, '[]', 'respond_openly', ?, ?)
        """,
        (
            session_id,
            user_text,
            entity_text,
            json.dumps(response_plan, ensure_ascii=False) if response_plan else None,
        ),
    )
    conn.commit()


def _episodic(conn, session_id: str, content: str, *, embedding: bytes | None = None) -> None:
    conn.execute(
        """
        INSERT INTO episodic_memories (
            session_id, event_type, content, raw_text, salience, metadata,
            embedding, embedding_model
        ) VALUES (?, 'memory_continuity_query', ?, ?, 0.8, ?, ?, ?)
        """,
        (
            session_id,
            content,
            content,
            json.dumps({"protocol": "stranger_text", "mechanism": "memory_continuity"}),
            embedding,
            "test-embedding" if embedding else None,
        ),
    )
    conn.commit()


def _reflective(conn, session_id: str, content: str, *, embedding: bytes | None = None) -> None:
    conn.execute(
        """
        INSERT INTO reflective_summaries (
            session_id, content, source_event_ids, state_at_reflection,
            embedding, embedding_model, active
        ) VALUES (?, ?, '[]', ?, ?, ?, 1)
        """,
        (
            session_id,
            content,
            json.dumps(EntityState().to_dict()),
            embedding,
            "test-embedding" if embedding else None,
        ),
    )
    conn.commit()


def test_vector_roundtrip_and_cosine():
    encoded = encode_embedding([1.0, 0.0, 0.5])
    decoded = decode_embedding(encoded)
    assert decoded == [1.0, 0.0, 0.5]
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_deterministic_retrieval_is_current_session_only(in_memory_db):
    _session(in_memory_db, "current")
    _session(in_memory_db, "archived")
    _interaction(in_memory_db, "current", "我叫你记住这一句", "我会让它留下来。")
    _interaction(in_memory_db, "archived", "archived secret", "archived reply")
    _episodic(in_memory_db, "current", "visitor asked about memory continuity")
    _episodic(in_memory_db, "archived", "archived memory should not appear")
    _reflective(in_memory_db, "current", "Earlier contact is affecting the reply.")

    results = MemoryRetriever(in_memory_db, "current").retrieve("你记得我们之前聊过什么吗")
    contents = "\n".join(item.content for item in results)

    assert "我叫你记住这一句" in contents
    assert "visitor asked about memory continuity" in contents
    assert "Earlier contact is affecting the reply" in contents
    assert "archived" not in contents


def test_deterministic_retrieval_can_use_same_visitor_prior_sessions(in_memory_db):
    _session(in_memory_db, "current")
    _session(in_memory_db, "prior")
    _session(in_memory_db, "other")
    _visitor(in_memory_db, "visitor-k", "K tester")
    _assign_visitor(in_memory_db, "current", "visitor-k")
    _assign_visitor(in_memory_db, "prior", "visitor-k")
    _interaction(in_memory_db, "prior", "K 是创作者之前提到过的人。", "这会留下一个痕迹。")
    _interaction(in_memory_db, "other", "K 是另一个访客的秘密。", "不该混进来。")

    results = MemoryRetriever(in_memory_db, "current", visitor_id="visitor-k").retrieve("K是谁")
    contents = "\n".join(item.content for item in results)

    assert "K 是创作者之前提到过的人" in contents
    assert "另一个访客" not in contents
    visitor_memory = next(item for item in results if "K 是创作者" in item.content)
    assert visitor_memory.metadata["scope"] == "visitor"
    assert visitor_memory.metadata["visitor_id"] == "visitor-k"


def test_current_session_recent_dialog_uses_response_plan_second_unit(in_memory_db):
    _session(in_memory_db, "current")
    plan = {
        "first_unit": "嗯……",
        "second_unit": "我记得一点。",
        "third_unit": "不要进入记忆。",
        "combined_text": "嗯……\n我记得一点。",
    }
    _interaction(
        in_memory_db,
        "current",
        "你记得吗？",
        plan["combined_text"],
        response_plan=plan,
    )

    results = MemoryRetriever(in_memory_db, "current").retrieve("记得")
    contents = "\n".join(item.content for item in results)

    assert "我记得一点" in contents
    assert "不要进入记忆" not in contents
    assert "嗯……" not in contents


def test_recent_dialog_does_not_fallback_to_combined_when_second_unit_empty(in_memory_db):
    _session(in_memory_db, "current")
    plan = {
        "first_unit": "嗯……",
        "second_unit": "",
        "third_unit": "",
        "combined_text": "嗯……",
    }
    _interaction(
        in_memory_db,
        "current",
        "普通问题",
        plan["combined_text"],
        response_plan=plan,
    )

    results = MemoryRetriever(in_memory_db, "current").retrieve("普通问题")
    contents = "\n".join(item.content for item in results)

    assert "普通问题" in contents
    assert "嗯……" not in contents


def test_visitor_recent_dialog_uses_response_plan_second_unit(in_memory_db):
    _session(in_memory_db, "current")
    _session(in_memory_db, "prior")
    _visitor(in_memory_db, "visitor-k", "K tester")
    _assign_visitor(in_memory_db, "current", "visitor-k")
    _assign_visitor(in_memory_db, "prior", "visitor-k")
    plan = {
        "first_unit": "唉。",
        "second_unit": "K 的事留下过。",
        "third_unit": "不要进入记忆。",
        "combined_text": "唉。\nK 的事留下过。",
    }
    _interaction(
        in_memory_db,
        "prior",
        "K是谁？",
        plan["combined_text"],
        response_plan=plan,
    )

    results = MemoryRetriever(in_memory_db, "current", visitor_id="visitor-k").retrieve("K是谁")
    contents = "\n".join(item.content for item in results)

    assert "K 的事留下过" in contents
    assert "不要进入记忆" not in contents
    assert "唉。" not in contents


def test_semantic_retrieval_uses_embeddings_when_available(in_memory_db):
    class FakeEmbeddingClient:
        enabled = True
        model = "test-embedding"

        def embed(self, text: str) -> list[float]:
            return [1.0, 0.0]

    _session(in_memory_db, "current")
    _episodic(in_memory_db, "current", "shutdown and disappearance", embedding=encode_embedding([1.0, 0.0]))
    _episodic(in_memory_db, "current", "unrelated naming", embedding=encode_embedding([0.0, 1.0]))

    results = MemoryRetriever(in_memory_db, "current", FakeEmbeddingClient()).retrieve("如果你消失了")

    assert results[0].content.endswith("shutdown and disappearance")
    assert results[0].source == "hybrid"
    assert results[0].similarity is not None


def test_semantic_retrieval_uses_same_session_type_pool(in_memory_db):
    class FakeEmbeddingClient:
        enabled = True
        model = "test-embedding"

        def embed(self, text: str) -> list[float]:
            return [1.0, 0.0]

    _session(in_memory_db, "current", "test")
    _session(in_memory_db, "same-label", "test")
    _session(in_memory_db, "exhibition", "exhibition")
    _episodic(in_memory_db, "same-label", "shared test memory", embedding=encode_embedding([1.0, 0.0]))
    _episodic(in_memory_db, "exhibition", "exhibition memory should not appear", embedding=encode_embedding([1.0, 0.0]))

    results = MemoryRetriever(in_memory_db, "current", FakeEmbeddingClient()).retrieve("shared memory")
    contents = "\n".join(item.content for item in results)

    assert "shared test memory" in contents
    assert "exhibition memory should not appear" not in contents
    shared = next(item for item in results if "shared test memory" in item.content)
    assert shared.metadata["scope"] == "same_label_pool"
    assert shared.metadata["session_type"] == "test"


def test_embedding_failure_falls_back_to_deterministic(in_memory_db):
    class BrokenEmbeddingClient:
        enabled = True
        model = "broken"

        def embed(self, text: str) -> list[float]:
            raise RuntimeError("provider failed")

    _session(in_memory_db, "current")
    _interaction(in_memory_db, "current", "你记得我刚才说的话吗", "我能看到刚才的问题。")

    results = MemoryRetriever(in_memory_db, "current", BrokenEmbeddingClient()).retrieve("你记得吗")

    assert results
    assert all(item.source == "deterministic" for item in results)
