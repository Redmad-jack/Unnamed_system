from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from conscious_entity.llm.claude_client import ClaudeClient
from conscious_entity.memory.episodic_store import EpisodicStore
from conscious_entity.memory.models import EpisodicMemory, ReflectiveSummary
from conscious_entity.memory.reflective_store import ReflectiveStore
from conscious_entity.reflection.compression_rules import should_reflect
from conscious_entity.state.state_core import EntityState

logger = logging.getLogger(__name__)


class ReflectionEngine:
    """
    Triggers LLM-based compression of episodic memories into reflective summaries.

    Called at the end of each turn. Uses ClaudeClient (same as ExpressionEngine
    but with the reflection system prompt and a cheaper model).

    LLM interface note: the only LLM call is inside reflect().
    To mock: inject a ClaudeClient whose complete() returns a deterministic string.

    Failure handling (per BACKEND_STRUCTURE §6):
    - If the LLM call fails, reflection is skipped for this turn (logged, not re-raised).
    """

    def __init__(
        self,
        client: ClaudeClient,
        prompts_dir: Path,
        reflection_threshold: int,
        session_id: str,
    ) -> None:
        self._client = client
        self._threshold = reflection_threshold
        self._session_id = session_id
        self._system_prompt = self._load_reflection_prompt(prompts_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def maybe_reflect(
        self,
        state: EntityState,
        episodic_store: EpisodicStore,
        reflective_store: ReflectiveStore,
    ) -> Optional[ReflectiveSummary]:
        """
        Check whether the reflection threshold has been reached.
        If so, run reflection and return the new ReflectiveSummary.
        Returns None if threshold not met or if reflection fails.
        """
        unreflected = episodic_store.get_unreflected()
        if not should_reflect(len(unreflected), self._threshold):
            return None
        return self.reflect(unreflected, state, episodic_store, reflective_store)

    def reflect(
        self,
        source_events: list[EpisodicMemory],
        state: EntityState,
        episodic_store: EpisodicStore,
        reflective_store: ReflectiveStore,
    ) -> Optional[ReflectiveSummary]:
        """
        Compress source_events into a ReflectiveSummary via LLM call.
        Stores the summary, marks source events as reflected.
        Returns None on LLM failure.
        """
        source_events_text = _format_source_events(source_events)
        state_text = _format_state(state)

        user_message = (
            self._system_prompt
            .replace("{source_events}", source_events_text)
            .replace("{state_at_reflection}", state_text)
        )

        # Reflection uses a single user turn (no conversation history needed).
        raw_text = self._client.complete(
            system="",
            messages=[{"role": "user", "content": user_message}],
            max_tokens=300,
        )

        if not raw_text:
            logger.error(
                "ReflectionEngine: LLM call failed, skipping reflection "
                "(unreflected events: %d)", len(source_events)
            )
            return None

        source_ids = [e.id for e in source_events if e.id is not None]
        summary = ReflectiveSummary(
            session_id=self._session_id,
            content=raw_text.strip(),
            source_event_ids=source_ids,
            state_at_reflection=state,
        )
        summary_id = reflective_store.store(summary)
        summary.id = summary_id

        for event in source_events:
            if event.id is not None:
                episodic_store.mark_reflected(event.id, summary_id)

        logger.debug(
            "ReflectionEngine: reflected %d events → summary id=%d",
            len(source_events),
            summary_id,
        )
        return summary

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_reflection_prompt(prompts_dir: Path) -> str:
        path = prompts_dir / "reflection_system.txt"
        if not path.exists():
            raise FileNotFoundError(f"Reflection prompt not found: {path}")
        return path.read_text(encoding="utf-8")


def _format_source_events(events: list[EpisodicMemory]) -> str:
    lines = []
    for i, e in enumerate(events, 1):
        ts = e.created_at.strftime("%H:%M:%S") if e.created_at else "?"
        line = f"{i}. [{ts}] {e.event_type}: {e.content}"
        if e.raw_text:
            line += f' (raw: "{e.raw_text}")'
        lines.append(line)
    return "\n".join(lines)


def _format_state(state: EntityState) -> str:
    return "\n".join(f"- {k}: {v:.2f}" for k, v in state.to_dict().items())
