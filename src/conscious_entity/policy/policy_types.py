from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PolicyAction(str, Enum):
    RESPOND_OPENLY = "respond_openly"
    RESPOND_BRIEFLY = "respond_briefly"
    ASK_BACK = "ask_back"
    DELAY_RESPONSE = "delay_response"
    REFUSE = "refuse"
    DIVERT_TOPIC = "divert_topic"
    RETRIEVE_MEMORY_FIRST = "retrieve_memory_first"
    ENTER_SILENCE_MODE = "enter_silence_mode"
    SHOW_VISUAL_DISTURBANCE = "show_visual_disturbance"


# Ordered from most to least permissive.
# Used by required_behaviors min_action_level checks.
_ACTION_LEVEL: dict[PolicyAction, int] = {
    PolicyAction.RESPOND_OPENLY: 0,
    PolicyAction.RESPOND_BRIEFLY: 1,
    PolicyAction.ASK_BACK: 2,
    PolicyAction.DELAY_RESPONSE: 3,
    PolicyAction.RETRIEVE_MEMORY_FIRST: 3,
    PolicyAction.DIVERT_TOPIC: 4,
    PolicyAction.REFUSE: 5,
    PolicyAction.SHOW_VISUAL_DISTURBANCE: 5,
    PolicyAction.ENTER_SILENCE_MODE: 6,
}


def action_level(action: PolicyAction) -> int:
    """Return restrictiveness level of an action (higher = more restrictive)."""
    return _ACTION_LEVEL.get(action, 0)


@dataclass
class PolicyDecision:
    action: PolicyAction
    delay_ms: int = 0
    retrieve_query: Optional[str] = None
    # Which rule fired — stored for debug and governance panel (v0.3)
    rationale: str = ""
    # Raw params from YAML rule (preserved for downstream consumers)
    params: dict = field(default_factory=dict)
