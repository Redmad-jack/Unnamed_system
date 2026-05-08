from __future__ import annotations

from typing import Any

from have_some_ai.models import Answer, Assignment, ObservationEvent
from have_some_ai.questionnaire import QuestionBank


class ScoringEngine:
    """Deterministic two-question food assignment."""

    def __init__(self, scoring_config: dict[str, Any], question_bank: QuestionBank) -> None:
        self._config = scoring_config
        self._question_bank = question_bank

    def assign(
        self,
        participant_id: str,
        answers: list[Answer],
        observations: list[ObservationEvent],
    ) -> Assignment:
        aimiao_score = 0.0
        soup_score = 0.0
        answer_breakdown: list[dict[str, Any]] = []
        soup_form: str | None = None
        variant: str | None = None

        for answer in answers:
            question = self._question_bank.get_question(answer.question_id)
            option = next((opt for opt in question.options if opt.id == answer.option_id), None)
            if option is None:
                raise ValueError(
                    f"Invalid option {answer.option_id} for question {answer.question_id}"
                )
            if question.module_id == "soup_salad":
                soup_form = "soup" if option.id == "A" else "salad"
                soup_score = 1.0 if soup_form == "soup" else -1.0
            elif question.module_id in {"normal_aimiao", "ai_trace"}:
                variant = "aimiao" if option.id == "A" else "normal"
                aimiao_score = 1.0 if variant == "aimiao" else 0.0
            answer_breakdown.append({
                "question_id": question.id,
                "module_id": question.module_id,
                "option_id": option.id,
                "axis": _axis_for_module(question.module_id),
            })

        observation_breakdown = []
        for event in observations:
            observation_breakdown.append({
                "event_type": event.event_type,
                "confidence": _clamp(float(event.confidence), 0.0, 1.0),
                "used_for_assignment": False,
            })

        if soup_form is None:
            raise ValueError("Missing soup/salad formal answer")
        if variant is None:
            raise ValueError("Missing normal/aimiao formal answer")

        food_code = self._food_code(soup_form, variant)
        food_label = str(self._config["foods"][food_code]["label"])

        rationale = {
            "answers": answer_breakdown,
            "observations": observation_breakdown,
            "mapping": {
                "soup_salad": soup_form,
                "normal_aimiao": variant,
            },
        }

        return Assignment(
            participant_id=participant_id,
            food_code=food_code,
            food_label=food_label,
            ai_trace_score=round(aimiao_score, 3),
            relational_score=round(soup_score, 3),
            rationale=rationale,
        )

    def _food_code(self, soup_form: str, variant: str) -> str:
        if variant == "aimiao" and soup_form == "soup":
            return "aimiao_soup"
        if variant == "aimiao" and soup_form == "salad":
            return "aimiao_salad"
        return soup_form


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _axis_for_module(module_id: str) -> str:
    if module_id == "soup_salad":
        return "soup_salad"
    if module_id in {"normal_aimiao", "ai_trace"}:
        return "normal_aimiao"
    return "ignored"
