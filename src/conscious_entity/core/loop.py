from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from conscious_entity.core.event_bus import EventBus
from conscious_entity.expression.context_builder import ContextBuilder
from conscious_entity.expression.expression_engine import ExpressionEngine
from conscious_entity.expression.output_model import ExpressionOutput
from conscious_entity.expression.style_mapper import StyleMapper
from conscious_entity.llm.claude_client import ClaudeClient
from conscious_entity.llm.embedding_client import EmbeddingClient, EmbeddingConfigurationError
from conscious_entity.memory.episodic_store import EpisodicStore
from conscious_entity.memory.managed import MemoryProvider, build_memory_provider
from conscious_entity.memory.models import EpisodicMemory, RetrievedMemory, ShortTermEntry
from conscious_entity.memory.reflective_store import ReflectiveStore
from conscious_entity.memory.retrieval import MemoryRetriever
from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.memory.vector import encode_embedding
from conscious_entity.perception.event_types import EventType, PerceptionEvent
from conscious_entity.perception.keyword_detector import KeywordDetector
from conscious_entity.perception.relationship_detector import RelationshipDetector
from conscious_entity.perception.salience_scorer import SalienceScorer
from conscious_entity.perception.text_parser import TextParser
from conscious_entity.policy.constitution import Constitution
from conscious_entity.policy.policy_selector import PolicySelector
from conscious_entity.policy.policy_types import PolicyAction, PolicyDecision
from conscious_entity.reflection.reflection_engine import ReflectionEngine
from conscious_entity.state.state_core import EntityState
from conscious_entity.state.state_engine import StateEngine
from conscious_entity.state.state_store import StateStore

logger = logging.getLogger(__name__)

# Per-turn elapsed seconds for the current decay model.
_DECAY_SECONDS_PER_TURN: float = 120.0


class InteractionLoop:
    """
    Orchestrates the full per-turn pipeline:

      1.  Parse input → events  (TextParser)
      2.  Add user turn to short-term memory
      3.  Apply events + decay  (StateEngine)
      4.  Preview managed memory influence and apply bounded state deltas
      5.  Save state snapshot   (StateStore)
      6.  Store significant events in episodic memory (EpisodicStore)
      7.  Select policy and apply managed memory policy influence
      8.  Retrieve memory when policy or managed memory asks for it
      9.  Generate expression   (ExpressionEngine)
      10. Add entity turn to short-term memory
      11. Log interaction and managed memory influence
      12. Propose and optionally auto-commit managed memory updates
      13. Maybe trigger reflection (ReflectionEngine)
      14. Emit events to EventBus for optional instrumentation
      Return ExpressionOutput

    LLM use is mediated through ClaudeClient in expression, reflection, and
    managed-memory proposal generation. Managed-memory behavior influence enters
    through preview/log/proposal/commit paths so it remains auditable.
    Pass `llm_client` to inject a mock for testing.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        config: dict[str, Any],           # output of load_all_configs()
        prompts_dir: Path,
        llm_client: Optional[ClaudeClient] = None,
        embedding_client: Optional[EmbeddingClient] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._conn = conn
        self._session_id = session_id
        self._event_bus = event_bus or EventBus()

        # --- Config extraction ---
        profile = config["entity_profile"]
        session_cfg = profile["session"]
        self._significant_salience: float = float(session_cfg.get("significant_salience", 0.5))
        self._reflection_threshold: int = int(session_cfg.get("reflection_threshold", 6))

        initial_state_dict = profile["initial_state"]
        self._initial_state = EntityState.from_dict(initial_state_dict)

        # --- Component assembly ---
        client = llm_client or ClaudeClient()

        self._state_engine = StateEngine(config["state_rules"])
        self._state_store = StateStore(conn, session_id)

        self._short_term = ShortTermMemory(
            max_turns=int(session_cfg.get("short_term_window", 10))
        )
        self._hydrate_short_term_from_log()
        self._episodic_store = EpisodicStore(conn, session_id)
        self._reflective_store = ReflectiveStore(conn, session_id)
        self._embedding_client = embedding_client if embedding_client is not None else _optional_embedding_client()
        self._managed_memory: MemoryProvider = build_memory_provider(
            conn,
            session_id,
            llm_client=client,
            embedding_client=self._embedding_client,
            prompts_dir=prompts_dir,
        )
        self._memory_retriever = MemoryRetriever(
            conn,
            session_id,
            self._embedding_client,
            managed_provider=self._managed_memory,
        )

        keyword_detector = KeywordDetector(profile.get("topics_of_sensitivity", []))
        salience_scorer = SalienceScorer(profile.get("salience_weights", {}))
        relationship_detector = RelationshipDetector(profile.get("text_protocol", {}))
        self._text_parser = TextParser(keyword_detector, salience_scorer, relationship_detector)
        self._salience_scorer = salience_scorer

        constitution = Constitution(config["constitution"])
        self._policy_selector = PolicySelector(config["policy_rules"], constitution)

        style_mapper = StyleMapper(config["expression_mappings"])
        context_builder = ContextBuilder(prompts_dir)
        self._expression_engine = ExpressionEngine(
            style_mapper, context_builder, client, constitution
        )

        self._reflection_engine = ReflectionEngine(
            client=client,
            prompts_dir=prompts_dir,
            reflection_threshold=self._reflection_threshold,
            session_id=session_id,
        )

        # Cache current state in memory to avoid extra DB reads within a session.
        self._current_state: Optional[EntityState] = self._state_store.load_latest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def current_state(self) -> EntityState:
        """Expose current state for CLI display and debug tools."""
        return self._current_state or self._initial_state

    def run_turn(self, raw_input: str) -> ExpressionOutput:
        """Run one user input through the managed-memory-aware turn pipeline."""

        # Parse input into perception events.
        state = self._current_state or self._initial_state
        events = self._text_parser.parse(raw_input, state, self._short_term)

        # Add user turn to short-term memory (before policy so repetition detection is accurate).
        self._short_term.add(ShortTermEntry(
            role="user",
            content=raw_input,
            timestamp=datetime.now(timezone.utc),
            event_type=events[0].event_type if events else None,
        ))

        # Apply events and per-turn decay before memory influence is previewed.
        new_state = state
        for event in events:
            new_state = self._state_engine.apply_event(new_state, event)
        new_state = self._state_engine.apply_decay(new_state, _DECAY_SECONDS_PER_TURN)

        memory_influence = self._managed_memory.preview_influence(
            raw_input,
            context={
                "events": [event.event_type.value for event in events],
                "state": new_state.to_dict(),
                "filters": {"session_type": self._session_type()},
            },
        )
        new_state = _apply_memory_state_influence(new_state, memory_influence)

        # Save the state that will drive this turn's policy and expression.
        trigger_types = ",".join(e.event_type.value for e in events)
        snapshot_id = self._state_store.save_snapshot(
            new_state,
            trigger_event_type=trigger_types or None,
        )
        self._current_state = new_state

        # Store significant events in episodic memory.
        for event in events:
            if event.salience >= self._significant_salience:
                content = _event_summary(event)
                mem = EpisodicMemory(
                    session_id=self._session_id,
                    event_type=event.event_type.value,
                    content=content,
                    raw_text=event.raw_text,
                    salience=event.salience,
                    state_snapshot_id=snapshot_id,
                    metadata=event.metadata,
                )
                try:
                    memory_id = self._episodic_store.store(mem)
                    self._store_episodic_embedding(memory_id, content)
                except Exception as exc:
                    logger.error("Failed to store episodic memory: %s", exc)

        # Select policy, then apply bounded managed-memory policy influence.
        decision = self._select_policy_with_managed_memory_influence(
            new_state, events, memory_influence
        )

        # Retrieve memory when policy or managed memory asks for it.
        decision, retrieved_memories = self._retrieve_memories_for_decision(
            decision, raw_input, events, memory_influence
        )

        # Generate expression.
        output = self._expression_engine.generate(
            policy=decision,
            state=new_state,
            short_term=self._short_term,
            retrieved_memories=retrieved_memories,
        )

        # Add entity turn to short-term memory.
        self._short_term.add(ShortTermEntry(
            role="entity",
            content=output.text,
            timestamp=datetime.now(timezone.utc),
        ))

        # Log interaction and managed memory influence.
        turn_id = self._log_interaction(
            role="user",
            raw_text=raw_input,
            events=events,
            decision=decision,
            output=output,
            snapshot_id=snapshot_id,
        )
        self._managed_memory.log_influence(
            turn_id=turn_id,
            query=raw_input,
            influence=memory_influence,
            state_snapshot_id=snapshot_id,
            policy_action=decision.action.value,
        )

        self._propose_and_commit_managed_memory(turn_id, events, decision)

        # Maybe trigger reflection.
        try:
            summary = self._reflection_engine.maybe_reflect(
                new_state, self._episodic_store, self._reflective_store
            )
            if summary is not None and summary.id is not None:
                self._store_reflective_embedding(summary.id, summary.content)
        except Exception as exc:
            logger.error("Reflection failed: %s", exc)

        # Emit to event bus for optional instrumentation
        self._event_bus.emit(
            "turn_complete",
            state=new_state,
            decision=decision,
            output=output,
        )

        return output

    def handle_system_event(
        self, event_type: EventType
    ) -> Optional[ExpressionOutput]:
        """
        Handle non-text events (USER_ENTERED, LONG_SILENCE_DETECTED, USER_LEFT).
        Updates state. May produce output or stay silent.
        """
        state = self._current_state or self._initial_state
        now = datetime.now(timezone.utc)

        salience = self._salience_scorer.score(event_type, None, state, self._short_term)
        event = PerceptionEvent(
            event_type=event_type,
            raw_text=None,
            timestamp=now,
            salience=salience,
        )

        new_state = self._state_engine.apply_event(state, event)
        new_state = self._state_engine.apply_decay(new_state, _DECAY_SECONDS_PER_TURN)
        self._state_store.save_snapshot(new_state, trigger_event_type=event_type.value)
        self._current_state = new_state

        self._event_bus.emit("system_event", event_type=event_type, state=new_state)

        # USER_ENTERED: the entity becomes aware of a presence but does not speak.
        # USER_LEFT: same — silent acknowledgement.
        # LONG_SILENCE_DETECTED may produce a very brief output in a future presence layer.
        return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _select_policy_with_managed_memory_influence(
        self,
        state: EntityState,
        events: list[PerceptionEvent],
        memory_influence: dict[str, Any],
    ) -> PolicyDecision:
        decision = self._policy_selector.select(state, events, self._short_term)
        suggested_action = memory_influence.get("policy_influence", {}).get("suggested_action")
        if (
            decision.action == PolicyAction.RESPOND_OPENLY
            and suggested_action == "retrieve_selective_memory"
        ):
            return PolicyDecision(
                action=PolicyAction.RETRIEVE_SELECTIVE_MEMORY,
                rationale=f"managed-memory:{decision.rationale}",
                params={**decision.params, "managed_memory": True, "retrieve_memory": True},
            )
        return decision

    def _retrieve_memories_for_decision(
        self,
        decision: PolicyDecision,
        raw_input: str,
        events: list[PerceptionEvent],
        memory_influence: dict[str, Any],
    ) -> tuple[PolicyDecision, list[RetrievedMemory]]:
        should_retrieve = (
            decision.action in {PolicyAction.RETRIEVE_MEMORY_FIRST, PolicyAction.RETRIEVE_SELECTIVE_MEMORY}
            or bool(decision.params.get("retrieve_memory"))
        )
        if should_retrieve:
            retrieved_memories = self._memory_retriever.retrieve(
                decision.retrieve_query or raw_input,
                events=events,
            )
        else:
            retrieved_memories = [
                _public_memory_to_retrieved(item)
                for item in memory_influence.get("expression_context", [])
                if isinstance(item, dict)
            ]

        if decision.action == PolicyAction.RETRIEVE_MEMORY_FIRST:
            decision = PolicyDecision(
                action=PolicyAction.RESPOND_OPENLY,
                rationale=f"post-retrieval:{decision.rationale}",
                params=decision.params,
            )
            logger.debug("RETRIEVE_MEMORY_FIRST: fetched %d memories", len(retrieved_memories))
        elif decision.action == PolicyAction.RETRIEVE_SELECTIVE_MEMORY:
            logger.debug(
                "RETRIEVE_SELECTIVE_MEMORY: fetched %d memories",
                len(retrieved_memories),
            )

        return decision, retrieved_memories

    def _propose_and_commit_managed_memory(
        self,
        turn_id: int | None,
        events: list[PerceptionEvent],
        decision: PolicyDecision,
    ) -> None:
        try:
            proposals = self._managed_memory.propose(
                _recent_messages_for_memory(self._short_term),
                context={
                    "turn_id": turn_id,
                    "source_turn_ids": [turn_id] if turn_id is not None else [],
                    "events": [event.event_type.value for event in events],
                    "policy_action": decision.action.value,
                },
            )
            if proposals and self._managed_memory.auto_commit:
                proposal_ids = [proposal.id for proposal in proposals if proposal.id is not None]
                self._managed_memory.commit(proposal_ids=proposal_ids)
        except Exception as exc:
            logger.error("Managed memory proposal/commit failed: %s", exc)

    def _hydrate_short_term_from_log(self) -> None:
        """Restore the recent dialog window for prompt continuity after restart."""
        limit = self._short_term.max_turns
        rows = self._conn.execute(
            """
            SELECT raw_text, expression_output, turn_at
            FROM interaction_log
            WHERE session_id = ?
            ORDER BY turn_at DESC, id DESC
            LIMIT ?
            """,
            (self._session_id, limit),
        ).fetchall()
        for row in reversed(rows):
            timestamp = _parse_timestamp(row["turn_at"])
            if row["raw_text"]:
                self._short_term.add(ShortTermEntry(
                    role="user",
                    content=row["raw_text"],
                    timestamp=timestamp,
                ))
            if row["expression_output"] is not None:
                self._short_term.add(ShortTermEntry(
                    role="entity",
                    content=row["expression_output"],
                    timestamp=timestamp,
                ))

    def _log_interaction(
        self,
        role: str,
        raw_text: str,
        events: list[PerceptionEvent],
        decision: PolicyDecision,
        output: ExpressionOutput,
        snapshot_id: int,
    ) -> int | None:
        event_types_json = json.dumps([e.event_type.value for e in events])
        try:
            cursor = self._conn.execute(
                """
                INSERT INTO interaction_log (
                    session_id, role, raw_text, event_types,
                    policy_action, expression_output, delay_ms,
                    visual_mode, state_snapshot_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._session_id,
                    role,
                    raw_text,
                    event_types_json,
                    decision.action.value,
                    output.text,
                    output.delay_ms,
                    output.visual_mode,
                    snapshot_id,
                ),
            )
            self._conn.commit()
            return int(cursor.lastrowid)
        except Exception as exc:
            logger.error("Failed to write interaction_log: %s", exc)
            return None

    def _store_episodic_embedding(self, memory_id: int, text: str) -> None:
        if self._embedding_client is None or not self._embedding_client.enabled:
            return
        model = self._embedding_client.model
        if not model:
            return
        try:
            embedding = encode_embedding(self._embedding_client.embed(text))
            self._episodic_store.update_embedding(memory_id, embedding, model)
        except Exception as exc:
            logger.warning("Failed to attach episodic embedding; continuing without it: %s", exc)

    def _store_reflective_embedding(self, summary_id: int, text: str) -> None:
        if self._embedding_client is None or not self._embedding_client.enabled:
            return
        model = self._embedding_client.model
        if not model:
            return
        try:
            embedding = encode_embedding(self._embedding_client.embed(text))
            self._reflective_store.update_embedding(summary_id, embedding, model)
        except Exception as exc:
            logger.warning("Failed to attach reflective embedding; continuing without it: %s", exc)

    def _session_type(self) -> str:
        row = self._conn.execute(
            "SELECT session_type FROM sessions WHERE id = ?",
            (self._session_id,),
        ).fetchone()
        if row and row["session_type"] in {"test", "exhibition"}:
            return str(row["session_type"])
        return "test"


def _event_summary(event: PerceptionEvent) -> str:
    if event.raw_text:
        return f"{event.event_type.value}: {event.raw_text[:200]}"
    return event.event_type.value


def _apply_memory_state_influence(state: EntityState, influence: dict[str, Any]) -> EntityState:
    state_influence = influence.get("state_influence", {}) if isinstance(influence, dict) else {}
    deltas = state_influence.get("deltas", {}) if isinstance(state_influence, dict) else {}
    if not isinstance(deltas, dict) or not deltas:
        return state
    values = state.to_dict()
    for key, delta in deltas.items():
        if key not in values:
            continue
        try:
            values[key] = values[key] + float(delta)
        except (TypeError, ValueError):
            continue
    return EntityState.from_dict(values).clamp_all()


def _public_memory_to_retrieved(item: dict[str, Any]) -> RetrievedMemory:
    return RetrievedMemory(
        memory_type="managed",
        content=str(item.get("content", "")),
        score=float(item.get("score", 0.0) or 0.0),
        source=str(item.get("source", "managed")),
        metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
    )


def _recent_messages_for_memory(short_term: ShortTermMemory) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for entry in short_term.get_recent(6):
        role = "assistant" if entry.role == "entity" else "user"
        messages.append({"role": role, "content": entry.content})
    return messages


def _parse_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)


def _optional_embedding_client() -> EmbeddingClient | None:
    try:
        return EmbeddingClient.from_env()
    except EmbeddingConfigurationError as exc:
        logger.warning("Embedding configuration ignored; deterministic memory retrieval remains active: %s", exc)
        return None
