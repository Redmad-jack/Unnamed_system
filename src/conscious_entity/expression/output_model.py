from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class UtterancePlan:
    text: str


@dataclass(frozen=True)
class SpeechPlan:
    first_unit: UtterancePlan
    second_unit: UtterancePlan
    third_unit: UtterancePlan
    combined_text: str


@dataclass(frozen=True)
class ResponsePlan:
    first_unit: str
    second_unit: str
    third_unit: str
    vocal_marker: str
    body_action: str
    visual_mode: str
    combined_text: str

    def to_dict(self) -> dict[str, str]:
        return {
            "first_unit": self.first_unit,
            "second_unit": self.second_unit,
            "third_unit": self.third_unit,
            "vocal_marker": self.vocal_marker,
            "body_action": self.body_action,
            "visual_mode": self.visual_mode,
            "combined_text": self.combined_text,
        }


def build_response_plan(
    *,
    first_unit: str,
    second_unit: str,
    third_unit: str,
    vocal_marker: str,
    body_action: str,
    visual_mode: str,
) -> ResponsePlan:
    clean_first = _clean_unit(first_unit)
    clean_second = _clean_unit(second_unit)
    clean_third = _clean_unit(third_unit)
    combined_text = _combine_units(clean_first, clean_second)
    speech = SpeechPlan(
        first_unit=UtterancePlan(clean_first),
        second_unit=UtterancePlan(clean_second),
        third_unit=UtterancePlan(clean_third),
        combined_text=combined_text,
    )
    return ResponsePlan(
        first_unit=speech.first_unit.text,
        second_unit=speech.second_unit.text,
        third_unit=speech.third_unit.text,
        vocal_marker=vocal_marker,
        body_action=body_action,
        visual_mode=visual_mode,
        combined_text=speech.combined_text,
    )


@dataclass
class ExpressionOutput:
    text: str
    delay_ms: int
    visual_mode: str
    spoken_text: Optional[str]  # Optional voice-channel text; falls back to text when None.
    raw_prompt: str         # full prompt serialized for debugging / governance panel
    vocal_marker: str = "none"
    body_action: str = "none"
    response_plan: Optional[ResponsePlan] = None
    truncated: bool = False
    stop_reason: Optional[str] = None
    latency_record_id: Optional[str] = None


def _clean_unit(text: str | None) -> str:
    return (text or "").strip()


def _combine_units(*units: str) -> str:
    return "\n".join(unit for unit in (_clean_unit(unit) for unit in units) if unit)
