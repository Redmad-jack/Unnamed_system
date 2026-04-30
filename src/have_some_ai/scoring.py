from __future__ import annotations

from typing import Any

from have_some_ai.models import Answer, Assignment, ObservationEvent
from have_some_ai.questionnaire import QuestionBank


class ScoringEngine:
    """Deterministic dual-axis scoring for food assignment."""

    def __init__(self, scoring_config: dict[str, Any], question_bank: QuestionBank) -> None:
        self._config = scoring_config
        self._question_bank = question_bank

    def assign(
        self,
        participant_id: str,
        answers: list[Answer],
        observations: list[ObservationEvent],
    ) -> Assignment:
        ai_trace_score = 0.0
        relational_score = 0.0
        answer_breakdown: list[dict[str, Any]] = []

        for answer in answers:
            question = self._question_bank.get_question(answer.question_id)
            option = next((opt for opt in question.options if opt.id == answer.option_id), None)
            if option is None:
                raise ValueError(
                    f"Invalid option {answer.option_id} for question {answer.question_id}"
                )
            ai_delta = float(option.scores.get("ai_trace", 0.0))
            relational_delta = float(option.scores.get("relational", 0.0))
            ai_trace_score += ai_delta
            relational_score += relational_delta
            answer_breakdown.append({
                "question_id": question.id,
                "module_id": question.module_id,
                "option_id": option.id,
                "ai_trace": ai_delta,
                "relational": relational_delta,
            })

        observation_breakdown = []
        observation_weights = self._config.get("observation_weights", {})
        for event in observations:
            weights = observation_weights.get(event.event_type)
            if not weights:
                continue
            confidence = _clamp(float(event.confidence), 0.0, 1.0)
            ai_delta = float(weights.get("ai_trace", 0.0)) * confidence
            relational_delta = float(weights.get("relational", 0.0)) * confidence
            ai_trace_score += ai_delta
            relational_score += relational_delta
            observation_breakdown.append({
                "event_type": event.event_type,
                "confidence": confidence,
                "ai_trace": ai_delta,
                "relational": relational_delta,
            })

        food_code = self._food_code(ai_trace_score, relational_score)
        food_label = str(self._config["foods"][food_code]["label"])

        rationale = {
            "answers": answer_breakdown,
            "observations": observation_breakdown,
            "thresholds": {
                "ai_sprout": self._ai_sprout_threshold,
                "soup": self._soup_threshold,
            },
        }

        return Assignment(
            participant_id=participant_id,
            food_code=food_code,
            food_label=food_label,
            ai_trace_score=round(ai_trace_score, 3),
            relational_score=round(relational_score, 3),
            rationale=rationale,
        )

    @property
    def _ai_sprout_threshold(self) -> float:
        return float(self._config["axes"]["ai_trace"].get("sprout_threshold", 2.0))

    @property
    def _soup_threshold(self) -> float:
        return float(self._config["axes"]["relational"].get("soup_threshold", 0.0))

    def _food_code(self, ai_trace_score: float, relational_score: float) -> str:
        has_sprout = ai_trace_score >= self._ai_sprout_threshold
        is_soup = relational_score >= self._soup_threshold
        if has_sprout and is_soup:
            return "ai_sprout_soup"
        if has_sprout and not is_soup:
            return "ai_sprout_salad"
        if not has_sprout and is_soup:
            return "soup"
        return "salad"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
