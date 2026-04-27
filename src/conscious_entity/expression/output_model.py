from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ExpressionOutput:
    text: str
    delay_ms: int
    visual_mode: str        # "normal" | "fragmented" | "disturbed" | "silent"
    spoken_text: Optional[str]  # v0.2 voice channel; always None in v0.1
    raw_prompt: str         # full prompt serialized for debugging / governance panel
    truncated: bool = False
    stop_reason: Optional[str] = None
    turn: Optional[dict[str, Any]] = None
