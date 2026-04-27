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
from conscious_entity.memory.episodic_store import EpisodicStore
from conscious_entity.memory.models import EpisodicMemory, ShortTermEntry
from conscious_entity.memory.reflective_store import ReflectiveStore
from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.perception.event_types import EventType, PerceptionEvent
from conscious_entity.perception.keyword_detector import KeywordDetector
from conscious_entity.perception.salience_scorer import SalienceScorer
from conscious_entity.perception.text_parser import TextParser
from conscious_entity.policy.constitution import Constitution
from conscious_entity.policy.policy_selector import PolicySelector
from conscious_entity.policy.policy_types import PolicyAction, PolicyDecision
from conscious_entity.reflection.reflection_engine import ReflectionEngine
from conscious_entity.shopkeeper.menu import MenuCatalog
from conscious_entity.shopkeeper.models import ShopSessionState, TurnInput
from conscious_entity.shopkeeper.prompt_builder import ShopkeeperPromptBuilder
from conscious_entity.shopkeeper.response_guard import ShopkeeperResponseGuard
from conscious_entity.shopkeeper.router import RouteDecision, ShopSceneRouter
from conscious_entity.shopkeeper.state_store import ShopStateStore
from conscious_entity.state.state_core import EntityState
from conscious_entity.state.state_engine import StateEngine
from conscious_entity.state.state_store import StateStore

logger = logging.getLogger(__name__)

# Per-turn elapsed seconds for v0.1 time-decay (clock-based decay is v0.2).
_DECAY_SECONDS_PER_TURN: float = 120.0


class InteractionLoop:
    """
    Orchestrates the full per-turn pipeline:

      1.  Parse input → events  (TextParser)
      2.  Load current state    (StateStore or initial_state)
      3.  Apply event + decay   (StateEngine)
      4.  Save state snapshot   (StateStore)
      5.  Store significant events in episodic memory (EpisodicStore)
      6.  Select policy         (PolicySelector)
      7.  If RETRIEVE_MEMORY_FIRST: fetch recent memories, switch to RESPOND_OPENLY
      8.  Generate expression   (ExpressionEngine)
      9.  Add entity turn to short-term memory
      10. Log interaction       (interaction_log table)
      11. Maybe trigger reflection (ReflectionEngine)
      12. Emit events to EventBus for optional instrumentation
      Return ExpressionOutput

    All LLM calls are isolated in ExpressionEngine and ReflectionEngine via ClaudeClient.
    Pass `llm_client` to inject a mock for testing.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        config: dict[str, Any],           # output of load_all_configs()
        prompts_dir: Path,
        llm_client: Optional[ClaudeClient] = None,
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
        self._episodic_store = EpisodicStore(conn, session_id)
        self._reflective_store = ReflectiveStore(conn, session_id)
        self._shop_state_store = ShopStateStore(conn, session_id)

        shopkeeper_cfg = config["shopkeeper_mode"]
        self._menu_catalog = MenuCatalog.from_config(shopkeeper_cfg)
        self._shop_router = ShopSceneRouter(shopkeeper_cfg, self._menu_catalog)
        self._shop_prompt_builder = ShopkeeperPromptBuilder(
            prompts_dir, shopkeeper_cfg, self._menu_catalog
        )

        keyword_detector = KeywordDetector(profile.get("topics_of_sensitivity", []))
        salience_scorer = SalienceScorer(profile.get("salience_weights", {}))
        self._text_parser = TextParser(keyword_detector, salience_scorer)
        self._salience_scorer = salience_scorer

        constitution = Constitution(config["constitution"])
        self._policy_selector = PolicySelector(config["policy_rules"], constitution)

        style_mapper = StyleMapper(config["expression_mappings"])
        context_builder = ContextBuilder(prompts_dir)
        self._expression_engine = ExpressionEngine(
            style_mapper,
            context_builder,
            client,
            constitution,
            response_guard=ShopkeeperResponseGuard(shopkeeper_cfg),
        )

        self._reflection_engine = ReflectionEngine(
            client=client,
            prompts_dir=prompts_dir,
            reflection_threshold=self._reflection_threshold,
            session_id=session_id,
        )

        # Cache current state in memory to avoid extra DB reads within a session.
        self._current_state: Optional[EntityState] = self._state_store.load_latest()
        self._current_shop_state: ShopSessionState = (
            self._shop_state_store.load_latest() or ShopSessionState()
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def current_state(self) -> EntityState:
        """Expose current state for CLI display and debug tools."""
        return self._current_state or self._initial_state

    @property
    def current_shop_state(self) -> ShopSessionState:
        """Expose current shopkeeper state for tests and developer tooling."""
        return self._current_shop_state

    def run_turn(self, raw_input: str | TurnInput) -> ExpressionOutput:
        """Run the full 12-step pipeline for one user input turn."""
        turn_input = _coerce_turn_input(raw_input)
        raw_text = turn_input.effective_text

        # Step 1: Parse input → events
        state = self._current_state or self._initial_state
        events = self._text_parser.parse(raw_text, state, self._short_term)

        # Add user turn to short-term memory (before policy so repetition detection is accurate).
        self._short_term.add(ShortTermEntry(
            role="user",
            content=raw_text,
            timestamp=datetime.now(timezone.utc),
            event_type=events[0].event_type if events else None,
        ))

        # Step 2 + 3: Apply events + per-turn decay → new state
        new_state = state
        for event in events:
            new_state = self._state_engine.apply_event(new_state, event)
        new_state = self._state_engine.apply_decay(new_state, _DECAY_SECONDS_PER_TURN)

        # Step 4: Save state snapshot
        trigger_types = ",".join(e.event_type.value for e in events)
        snapshot_id = self._state_store.save_snapshot(
            new_state,
            trigger_event_type=trigger_types or None,
        )
        self._current_state = new_state

        route = self._shop_router.route(
            turn_input, self._current_shop_state, self._short_term, new_state
        )

        # Step 5: Store significant events in episodic memory
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
                    metadata=_event_metadata(event, route),
                )
                try:
                    self._episodic_store.store(mem)
                except Exception as exc:
                    logger.error("Failed to store episodic memory: %s", exc)

        # Step 6: Select policy
        decision = self._policy_selector.select(new_state, events, self._short_term)

        # Step 7: If RETRIEVE_MEMORY_FIRST → fetch recent memories, switch action
        retrieved_memories: list = []
        if decision.action == PolicyAction.RETRIEVE_MEMORY_FIRST:
            retrieved_memories = _get_recent_memories(self._episodic_store)
            decision = PolicyDecision(
                action=PolicyAction.RESPOND_OPENLY,
                rationale=f"post-retrieval:{decision.rationale}",
            )
            logger.debug("RETRIEVE_MEMORY_FIRST: fetched %d memories", len(retrieved_memories))

        # Step 8: Generate expression
        shop_prompt = self._shop_prompt_builder.build(
            route=route,
            shop_state=route.next_state,
            entity_state=new_state,
            user_input=raw_text,
            retrieved_context=_retrieved_context_texts(
                turn_input.retrieved_context,
                retrieved_memories,
            ),
        )
        output = self._expression_engine.generate(
            policy=decision,
            state=new_state,
            short_term=self._short_term,
            retrieved_memories=retrieved_memories,
            prompt_context=shop_prompt,
            structured_turn=route.structured_turn(),
        )

        # Step 9: Add entity turn to short-term memory
        self._short_term.add(ShortTermEntry(
            role="entity",
            content=output.text,
            timestamp=datetime.now(timezone.utc),
        ))

        self._shop_state_store.save_snapshot(
            route.next_state,
            state_updates=route.state_updates,
            trigger_scene=route.scene.value,
            action=route.action.value,
            entity_state_snapshot_id=snapshot_id,
        )
        self._current_shop_state = route.next_state

        # Step 10: Log interaction
        self._log_interaction(
            role="user",
            raw_text=raw_text,
            events=events,
            decision=decision,
            output=output,
            snapshot_id=snapshot_id,
        )

        # Step 11: Maybe trigger reflection
        try:
            self._reflection_engine.maybe_reflect(
                new_state, self._episodic_store, self._reflective_store
            )
        except Exception as exc:
            logger.error("Reflection failed: %s", exc)

        # Emit to event bus for optional instrumentation
        self._event_bus.emit(
            "turn_complete",
            state=new_state,
            shop_state=route.next_state,
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
        # LONG_SILENCE_DETECTED: may produce a very brief output in future (v0.2).
        return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _log_interaction(
        self,
        role: str,
        raw_text: str,
        events: list[PerceptionEvent],
        decision: PolicyDecision,
        output: ExpressionOutput,
        snapshot_id: int,
    ) -> None:
        event_types_json = json.dumps([e.event_type.value for e in events])
        try:
            self._conn.execute(
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
        except Exception as exc:
            logger.error("Failed to write interaction_log: %s", exc)


def _event_summary(event: PerceptionEvent) -> str:
    if event.raw_text:
        return f"{event.event_type.value}: {event.raw_text[:200]}"
    return event.event_type.value


def _get_recent_memories(episodic_store: EpisodicStore) -> list[EpisodicMemory]:
    """v0.1 retrieval: recency-based (no embedding search)."""
    return episodic_store.get_recent(limit=5)


def _coerce_turn_input(raw_input: str | TurnInput) -> TurnInput:
    if isinstance(raw_input, TurnInput):
        return raw_input
    return TurnInput(text=str(raw_input))


def _event_metadata(event: PerceptionEvent, route: RouteDecision) -> dict:
    metadata = dict(event.metadata)
    metadata.update({
        "language": route.language.value,
        "scene": route.scene.value,
        "shop_action": route.action.value,
        "selected_soup": route.state_updates.get("selected_soup"),
    })
    return metadata


def _retrieved_context_texts(
    explicit_context: list[str],
    retrieved_memories: list[EpisodicMemory],
) -> list[str]:
    texts = [str(item) for item in explicit_context if str(item).strip()]
    for mem in retrieved_memories:
        if mem.content:
            texts.append(mem.content)
    return texts[:8]
