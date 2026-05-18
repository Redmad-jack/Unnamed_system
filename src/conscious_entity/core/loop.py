from __future__ import annotations

import json
import logging
import sqlite3
import threading
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from conscious_entity.core.event_bus import EventBus
from conscious_entity.db.connection import get_connection
from conscious_entity.expression.context_builder import ContextBuilder
from conscious_entity.expression.expression_engine import ExpressionEngine
from conscious_entity.expression.output_model import ExpressionOutput, build_response_plan
from conscious_entity.expression.style_mapper import StyleMapper
from conscious_entity.harness import HarnessLayer, HarnessTraceRecorder, get_harness_trace_store
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
from conscious_entity.telemetry.latency import (
    TurnLatencyRecorder,
    activate_turn_recorder,
    get_latency_tracker,
    turn_step,
)

logger = logging.getLogger(__name__)

# Per-turn elapsed seconds for the current decay model.
_DECAY_SECONDS_PER_TURN: float = 120.0


class InteractionLoop:
    """
    Orchestrates the full per-turn pipeline:

      1.  Parse input → events  (TextParser)
      2.  Apply events + decay  (StateEngine)
      3.  Generate first response unit with fast LLM, before memory writes/retrieval
      4.  Add user turn to short-term memory for the main expression path
      5.  Preview managed memory influence and apply bounded state deltas
      6.  Save state snapshot   (StateStore)
      7.  Store significant events in episodic memory (EpisodicStore)
      8.  Select policy and apply managed memory policy influence
      9.  Retrieve memory when policy or managed memory asks for it
      10. Generate expression   (ExpressionEngine)
      11. Add entity turn to short-term memory
      12. Log interaction and managed memory influence
      13. Propose and optionally auto-commit managed memory updates
      14. Maybe trigger reflection (ReflectionEngine)
      15. Emit events to EventBus for optional instrumentation
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
        visitor_id: str | None = None,
    ) -> None:
        self._conn = conn
        self._session_id = session_id
        self._visitor_id = visitor_id or _visitor_id_for_session(conn, session_id)
        self._event_bus = event_bus or EventBus()
        self._config = config
        self._prompts_dir = prompts_dir

        # --- Config extraction ---
        profile = config["entity_profile"]
        session_cfg = profile["session"]
        self._significant_salience: float = float(session_cfg.get("significant_salience", 0.5))
        self._reflection_threshold: int = int(session_cfg.get("reflection_threshold", 6))

        initial_state_dict = profile["initial_state"]
        self._initial_state = EntityState.from_dict(initial_state_dict)

        # --- Component assembly ---
        client = llm_client or ClaudeClient()
        self._llm_client = client

        self._state_engine = StateEngine(config["state_rules"])
        self._state_store = StateStore(conn, session_id)

        self._short_term = ShortTermMemory(
            max_turns=int(session_cfg.get("short_term_window", 10))
        )
        self._hydrate_short_term_from_log()
        self._episodic_store = EpisodicStore(conn, session_id, visitor_id=self._visitor_id)
        self._reflective_store = ReflectiveStore(conn, session_id, visitor_id=self._visitor_id)
        self._embedding_client = embedding_client if embedding_client is not None else _optional_embedding_client()
        self._background_db_path = _database_path_for_background(conn)
        self._background_executor: ThreadPoolExecutor | None = (
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="entity-memory-bg")
            if self._background_db_path is not None
            else None
        )
        self._background_futures: list[Future] = []
        self._background_lock = threading.Lock()
        self._managed_memory: MemoryProvider = build_memory_provider(
            conn,
            session_id,
            visitor_id=self._visitor_id,
            llm_client=client,
            embedding_client=self._embedding_client,
            prompts_dir=prompts_dir,
        )
        self._memory_retriever = MemoryRetriever(
            conn,
            session_id,
            self._embedding_client,
            managed_provider=self._managed_memory,
            visitor_id=self._visitor_id,
        )

        keyword_detector = KeywordDetector(profile.get("topics_of_sensitivity", []))
        salience_scorer = SalienceScorer(profile.get("salience_weights", {}))
        relationship_detector = RelationshipDetector(profile.get("text_protocol", {}))
        self._text_parser = TextParser(keyword_detector, salience_scorer, relationship_detector)
        self._salience_scorer = salience_scorer

        constitution = Constitution(config["constitution"])
        self._policy_selector = PolicySelector(config["policy_rules"], constitution)

        style_mapper = StyleMapper(config["expression_mappings"])
        self._style_mapper = style_mapper
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

    def run_turn(
        self,
        raw_input: str,
        source: str = "dialog",
        input_metadata: dict[str, Any] | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> ExpressionOutput:
        """Run one user input through the managed-memory-aware turn pipeline."""
        turn_metadata = dict(input_metadata or {})
        turn_metadata.setdefault("source", source)
        harness_recorder = HarnessTraceRecorder(
            session_id=self._session_id,
            source=source,
            metadata={
                "input_chars": len(raw_input),
                "input_mode": turn_metadata.get("input_mode") or "text",
                "visitor_id": self._visitor_id,
                "identity_session": (
                    turn_metadata.get("identity_session")
                    if isinstance(turn_metadata.get("identity_session"), dict)
                    else None
                ),
            },
        )
        recorder = TurnLatencyRecorder(
            source=source,
            metadata={
                "session_id": self._session_id,
                "visitor_id": self._visitor_id,
                "input_chars": len(raw_input),
                "input_mode": turn_metadata.get("input_mode"),
            },
        )
        success = False
        error: str | None = None
        with activate_turn_recorder(recorder):
            try:
                # Parse input into perception events.
                state = self._current_state or self._initial_state
                with recorder.step("perception.parse"):
                    events = self._text_parser.parse(raw_input, state, self._short_term)
                harness_recorder.record(
                    HarnessLayer.INPUT,
                    status="tagged",
                    decision=(
                        turn_metadata.get("identity_session", {}).get("session_decision")
                        if isinstance(turn_metadata.get("identity_session"), dict)
                        else None
                    ),
                    summary="User input accepted and parsed into perception events.",
                    metadata={
                        "source": source,
                        "input_mode": turn_metadata.get("input_mode") or "text",
                        "visitor_id": self._visitor_id,
                        "identity_session": (
                            turn_metadata.get("identity_session")
                            if isinstance(turn_metadata.get("identity_session"), dict)
                            else None
                        ),
                        "chars": len(raw_input),
                        "event_types": [event.event_type.value for event in events],
                    },
                )

                # Apply events and per-turn decay before any memory influence is previewed.
                with recorder.step("state.apply_events_and_decay"):
                    new_state = state
                    for event in events:
                        new_state = self._state_engine.apply_event(new_state, event)
                    new_state = self._state_engine.apply_decay(new_state, _DECAY_SECONDS_PER_TURN)

                with recorder.step("expression.plan_first_unit"):
                    first_unit = self._expression_engine.plan_first_unit(
                        raw_input,
                        new_state,
                        events,
                        short_term=self._short_term,
                    )
                    first_style = self._style_mapper.map(
                        new_state,
                        PolicyDecision(action=PolicyAction.RESPOND_OPENLY),
                    )
                    _emit_progress_event(
                        progress_callback,
                        {
                            "phase": "first_unit",
                            "text": first_unit,
                            "response_plan": build_response_plan(
                                first_unit=first_unit,
                                second_unit="",
                                third_unit="",
                                vocal_marker=first_style.vocal_marker,
                                body_action=first_style.body_action,
                                visual_mode=first_style.visual_mode,
                            ).to_dict(),
                            "events": [event.event_type.value for event in events],
                            "vocal_marker": first_style.vocal_marker,
                            "body_action": first_style.body_action,
                            "visual_mode": first_style.visual_mode,
                        },
                    )

                # Add user turn after the fast first-unit LLM so that first unit
                # cannot depend on short-term memory contents from this turn.
                with recorder.step("short_term.add_user"):
                    self._short_term.add(ShortTermEntry(
                        role="user",
                        content=raw_input,
                        timestamp=datetime.now(timezone.utc),
                        event_type=events[0].event_type if events else None,
                        metadata=turn_metadata,
                    ))

                with recorder.step("managed_memory.preview_influence"):
                    memory_influence = self._managed_memory.preview_influence(
                        raw_input,
                        context={
                            "events": [event.event_type.value for event in events],
                            "state": new_state.to_dict(),
                            "filters": {"session_type": self._session_type()},
                            "visitor_id": self._visitor_id,
                        },
                    )
                    new_state = _apply_memory_state_influence(new_state, memory_influence)
                policy_influence = memory_influence.get("policy_influence", {})
                state_influence = memory_influence.get("state_influence", {})
                harness_recorder.record(
                    HarnessLayer.MEMORY,
                    status="previewed",
                    decision=(
                        policy_influence.get("suggested_action")
                        if isinstance(policy_influence, dict)
                        else None
                    ),
                    summary="Managed memory influence previewed for this turn.",
                    metadata={
                        "expression_context_count": len(memory_influence.get("expression_context", [])),
                        "policy_suggestion": (
                            policy_influence.get("suggested_action")
                            if isinstance(policy_influence, dict)
                            else None
                        ),
                        "state_delta_keys": sorted(
                            (
                                state_influence.get("deltas", {})
                                if isinstance(state_influence, dict)
                                else {}
                            ).keys()
                        ),
                    },
                )

                # Save the state that will drive this turn's policy and expression.
                trigger_types = ",".join(e.event_type.value for e in events)
                with recorder.step("state.save_snapshot"):
                    snapshot_id = self._state_store.save_snapshot(
                        new_state,
                        trigger_event_type=trigger_types or None,
                    )
                    self._current_state = new_state
                harness_recorder.record(
                    HarnessLayer.STATE,
                    status="applied",
                    summary="State rules, decay, and bounded memory deltas were applied.",
                    metadata={
                        "snapshot_id": snapshot_id,
                        "trigger_event_types": trigger_types.split(",") if trigger_types else [],
                        "changed_fields": _changed_state_keys(state, new_state),
                    },
                )

                # Store significant events in episodic memory.
                with recorder.step("episodic_memory.store_significant"):
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
                with recorder.step("policy.select"):
                    decision = self._select_policy_with_managed_memory_influence(
                        new_state, events, memory_influence, harness_recorder
                )

                # Retrieve memory when policy or managed memory asks for it.
                retrieval_requested = (
                    decision.action in {
                        PolicyAction.RETRIEVE_MEMORY_FIRST,
                        PolicyAction.RETRIEVE_SELECTIVE_MEMORY,
                    }
                    or bool(decision.params.get("retrieve_memory"))
                )
                with recorder.step("memory.retrieve_for_decision"):
                    decision, retrieved_memories = self._retrieve_memories_for_decision(
                        decision, raw_input, events, memory_influence
                    )
                harness_recorder.record(
                    HarnessLayer.MEMORY,
                    status="retrieved",
                    decision=decision.action.value,
                    summary="Memory retrieval path resolved for the selected policy.",
                    metadata={
                        "retrieved_count": len(retrieved_memories),
                        "used_retriever": retrieval_requested,
                    },
                )

                # Generate expression.
                second_style = self._style_mapper.map(new_state, decision)

                def second_delta_callback(event: dict[str, Any]) -> None:
                    _emit_progress_event(
                        progress_callback,
                        {
                            "phase": "second_delta",
                            "text": str(event.get("text") or ""),
                            "index": int(event.get("index") or 0),
                            "policy_action": decision.action.value,
                            "visual_mode": second_style.visual_mode,
                            "vocal_marker": second_style.vocal_marker,
                            "body_action": second_style.body_action,
                        },
                    )

                with recorder.step("expression.generate"):
                    output = self._expression_engine.generate(
                        policy=decision,
                        state=new_state,
                        short_term=self._short_term,
                        retrieved_memories=retrieved_memories,
                        first_unit=first_unit,
                        harness_recorder=harness_recorder,
                        second_delta_callback=(
                            second_delta_callback if progress_callback is not None else None
                        ),
                    )
                harness_recorder.record(
                    HarnessLayer.PRESENTATION,
                    status="prepared",
                    decision=decision.action.value,
                    summary="ExpressionOutput prepared for the presentation layer.",
                    metadata={
                        "delay_ms": output.delay_ms,
                        "visual_mode": output.visual_mode,
                        "vocal_marker": output.vocal_marker,
                        "body_action": output.body_action,
                        "has_spoken_text": output.spoken_text is not None,
                        "response_plan": (
                            output.response_plan.to_dict()
                            if output.response_plan is not None
                            else None
                        ),
                        "text_chars": len(output.text),
                        "source": source,
                    },
                )

                # Add entity turn to short-term memory.
                with recorder.step("short_term.add_entity"):
                    self._short_term.add(ShortTermEntry(
                        role="entity",
                        content=_memory_text_for_output(output),
                        timestamp=datetime.now(timezone.utc),
                        metadata={
                            "response_plan": output.response_plan.to_dict()
                            if output.response_plan is not None
                            else None
                        },
                    ))

                # Log interaction and managed memory influence.
                with recorder.step("interaction_log.write"):
                    turn_id = self._log_interaction(
                        role="user",
                        raw_text=raw_input,
                        events=events,
                        decision=decision,
                        output=output,
                        snapshot_id=snapshot_id,
                    )
                with recorder.step("managed_memory.log_influence"):
                    self._managed_memory.log_influence(
                        turn_id=turn_id,
                        query=raw_input,
                        influence=memory_influence,
                        state_snapshot_id=snapshot_id,
                        policy_action=decision.action.value,
                    )

                with recorder.step("managed_memory.background_enqueue", blocking=False):
                    self._enqueue_managed_memory_maintenance(turn_id, events, decision)

                # Maybe trigger reflection.
                with recorder.step("reflection.maybe_reflect"):
                    try:
                        summary = self._reflection_engine.maybe_reflect(
                            new_state, self._episodic_store, self._reflective_store
                        )
                        if summary is not None and summary.id is not None:
                            self._store_reflective_embedding(summary.id, summary.content)
                    except Exception as exc:
                        logger.error("Reflection failed: %s", exc)

                # Emit to event bus for optional instrumentation.
                with recorder.step("event_bus.emit_turn_complete"):
                    self._event_bus.emit(
                        "turn_complete",
                        state=new_state,
                        decision=decision,
                        output=output,
                    )

                success = True
                return output
            except Exception as exc:
                error = str(exc)
                raise
            finally:
                get_harness_trace_store().record(
                    harness_recorder.finish(success=success, error=error)
                )
                get_latency_tracker().record_turn(
                    recorder.finish(success=success, error=error)
                )

    def flush_background_tasks(self) -> None:
        """Wait for queued post-turn maintenance tasks; intended for tests and shutdown."""
        with self._background_lock:
            futures = list(self._background_futures)
            self._background_futures.clear()
        if not futures:
            return
        wait(futures)
        for future in futures:
            future.result()

    def close(self, *, wait_for_background: bool = True) -> None:
        if wait_for_background:
            self.flush_background_tasks()
        if self._background_executor is not None:
            self._background_executor.shutdown(
                wait=wait_for_background,
                cancel_futures=not wait_for_background,
            )
            self._background_executor = None

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
        harness_recorder: HarnessTraceRecorder | None = None,
    ) -> PolicyDecision:
        decision = self._policy_selector.select(
            state,
            events,
            self._short_term,
            harness_recorder=harness_recorder,
        )
        suggested_action = memory_influence.get("policy_influence", {}).get("suggested_action")
        if (
            decision.action == PolicyAction.RESPOND_OPENLY
            and suggested_action == "retrieve_selective_memory"
        ):
            if harness_recorder is not None:
                harness_recorder.record(
                    HarnessLayer.POLICY,
                    status="selected",
                    rule_ids=["managed_memory:policy_influence"],
                    decision=PolicyAction.RETRIEVE_SELECTIVE_MEMORY.value,
                    summary="Managed memory influence upgraded policy to selective retrieval.",
                    metadata={
                        "previous_action": decision.action.value,
                        "suggested_action": suggested_action,
                    },
                )
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
            memory_context_allowed = _managed_memory_context_allowed(memory_influence)
            retrieved_memories = (
                [
                    _public_memory_to_retrieved(item)
                    for item in memory_influence.get("expression_context", [])
                    if isinstance(item, dict)
                ]
                if memory_context_allowed
                else []
            )
            if self._visitor_id and memory_context_allowed:
                visitor_hits = [
                    item
                    for item in self._memory_retriever.retrieve(raw_input, events=events, limit=5)
                    if item.metadata.get("scope") == "visitor" and item.score >= 0.2
                ]
                retrieved_memories.extend(visitor_hits[:3])

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
                    "visitor_id": self._visitor_id,
                },
            )
            if proposals and self._managed_memory.auto_commit:
                proposal_ids = [proposal.id for proposal in proposals if proposal.id is not None]
                with turn_step("managed_memory.commit"):
                    self._managed_memory.commit(proposal_ids=proposal_ids)
        except Exception as exc:
            logger.error("Managed memory proposal/commit failed: %s", exc)

    def _enqueue_managed_memory_maintenance(
        self,
        turn_id: int | None,
        events: list[PerceptionEvent],
        decision: PolicyDecision,
    ) -> None:
        if self._background_executor is None or self._background_db_path is None:
            self._propose_and_commit_managed_memory(turn_id, events, decision)
            return
        messages = _recent_messages_for_memory(self._short_term)
        context = {
            "turn_id": turn_id,
            "source_turn_ids": [turn_id] if turn_id is not None else [],
            "events": [event.event_type.value for event in events],
            "policy_action": decision.action.value,
            "visitor_id": self._visitor_id,
        }
        future = self._background_executor.submit(
            _run_managed_memory_maintenance,
            db_path=self._background_db_path,
            session_id=self._session_id,
            visitor_id=self._visitor_id,
            llm_client=self._llm_client,
            embedding_client=self._embedding_client,
            prompts_dir=self._prompts_dir,
            messages=messages,
            context=context,
        )
        future.add_done_callback(_log_background_task_result)
        with self._background_lock:
            self._background_futures = [
                item for item in self._background_futures if not item.done()
            ]
            self._background_futures.append(future)

    def _hydrate_short_term_from_log(self) -> None:
        """Restore the recent dialog window for prompt continuity after restart."""
        limit = self._short_term.max_turns
        rows = self._conn.execute(
            """
            SELECT raw_text, expression_output, response_plan_json, turn_at
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
            response_plan = _response_plan_from_response_plan_json(row["response_plan_json"])
            plan_second_unit = str(response_plan.get("second_unit") or "").strip() if response_plan else None
            entity_text = (
                plan_second_unit
                if plan_second_unit is not None
                else row["expression_output"]
            )
            if entity_text is not None:
                self._short_term.add(ShortTermEntry(
                    role="entity",
                    content=entity_text,
                    timestamp=timestamp,
                    metadata={"response_plan": response_plan} if response_plan else {},
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
                    session_id, visitor_id, role, raw_text, event_types,
                    policy_action, expression_output, response_plan_json,
                    delay_ms, visual_mode, state_snapshot_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._session_id,
                    self._visitor_id,
                    role,
                    raw_text,
                    event_types_json,
                    decision.action.value,
                    output.text,
                    (
                        json.dumps(output.response_plan.to_dict(), ensure_ascii=False)
                        if output.response_plan is not None
                        else None
                    ),
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
            with turn_step("embedding.episodic_store"):
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
            with turn_step("embedding.reflective_store"):
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


def _emit_progress_event(
    callback: Callable[[dict[str, Any]], None] | None,
    event: dict[str, Any],
) -> None:
    if callback is None:
        return
    try:
        callback(event)
    except Exception as exc:
        logger.warning("Progress callback failed; continuing turn: %s", exc)


def _memory_text_for_output(output: ExpressionOutput) -> str:
    if output.response_plan is not None:
        return (output.response_plan.second_unit or "").strip()
    return output.text


def _managed_memory_context_allowed(memory_influence: dict[str, Any]) -> bool:
    policy_influence = memory_influence.get("policy_influence", {})
    if isinstance(policy_influence, dict) and policy_influence.get("memory_gravity_gate_passed"):
        return True
    explanation = memory_influence.get("explanation", {})
    if isinstance(explanation, dict):
        gate = explanation.get("memory_gravity_gate", {})
        return isinstance(gate, dict) and bool(gate.get("passed"))
    return False


def _second_unit_from_response_plan_json(raw: str | None) -> str | None:
    parsed = _response_plan_from_response_plan_json(raw)
    if not parsed:
        return None
    return str(parsed.get("second_unit") or "").strip()


def _response_plan_from_response_plan_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _changed_state_keys(before: EntityState, after: EntityState) -> list[str]:
    before_values = before.to_dict()
    after_values = after.to_dict()
    return sorted(
        key
        for key, value in after_values.items()
        if before_values.get(key) != value
    )


def _public_memory_to_retrieved(item: dict[str, Any]) -> RetrievedMemory:
    return RetrievedMemory(
        memory_type="managed",
        content=str(item.get("content", "")),
        score=float(item.get("score", 0.0) or 0.0),
        source=str(item.get("source", "managed")),
        metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
    )


def _database_path_for_background(conn: sqlite3.Connection) -> Path | None:
    try:
        rows = conn.execute("PRAGMA database_list").fetchall()
    except sqlite3.Error:
        return None
    for row in rows:
        name = row["name"] if isinstance(row, sqlite3.Row) else row[1]
        file_path = row["file"] if isinstance(row, sqlite3.Row) else row[2]
        if name == "main" and file_path:
            return Path(str(file_path))
    return None


def _run_managed_memory_maintenance(
    *,
    db_path: Path,
    session_id: str,
    visitor_id: str | None,
    llm_client: ClaudeClient | None,
    embedding_client: EmbeddingClient | None,
    prompts_dir: Path,
    messages: list[dict],
    context: dict[str, Any],
) -> None:
    conn = get_connection(db_path, check_same_thread=False)
    try:
        provider = build_memory_provider(
            conn,
            session_id,
            visitor_id=visitor_id,
            llm_client=llm_client,
            embedding_client=embedding_client,
            prompts_dir=prompts_dir,
        )
        proposals = provider.propose(messages, context)
        if proposals and provider.auto_commit:
            proposal_ids = [proposal.id for proposal in proposals if proposal.id is not None]
            provider.commit(proposal_ids=proposal_ids)
    finally:
        conn.close()


def _log_background_task_result(future: Future) -> None:
    try:
        future.result()
    except Exception as exc:
        logger.error("Managed memory background task failed: %s", exc)


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


def _visitor_id_for_session(conn: sqlite3.Connection, session_id: str) -> str | None:
    try:
        row = conn.execute(
            "SELECT visitor_id FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    value = row["visitor_id"] if isinstance(row, sqlite3.Row) else row[0]
    return str(value) if value else None
