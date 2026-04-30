from __future__ import annotations

import random
from typing import Any, Iterable

from have_some_ai.models import Option, Question


class QuestionBank:
    """Structured question bank with one random draw per configured module."""

    def __init__(self, config: dict[str, Any], rng: random.Random | None = None) -> None:
        self._rng = rng or random.SystemRandom()
        self._modules = config.get("modules", [])
        self._questions_by_id = self._index_questions(self._modules)

    def draw_questions(self) -> list[Question]:
        drawn: list[Question] = []
        for module in self._modules:
            module_id = str(module["id"])
            module_label = str(module.get("label", module_id))
            draw_count = int(module.get("draw_count", 1))
            questions = [
                self._to_question(module_id, module_label, item)
                for item in module.get("questions", [])
            ]
            if draw_count > len(questions):
                raise ValueError(f"Module {module_id} cannot draw {draw_count} questions")
            drawn.extend(self._rng.sample(questions, draw_count))
        return drawn

    def get_question(self, question_id: str) -> Question:
        try:
            return self._questions_by_id[question_id]
        except KeyError as exc:
            raise KeyError(f"Unknown question id: {question_id}") from exc

    def iter_questions(self) -> Iterable[Question]:
        return self._questions_by_id.values()

    @staticmethod
    def _index_questions(modules: list[dict[str, Any]]) -> dict[str, Question]:
        questions: dict[str, Question] = {}
        for module in modules:
            module_id = str(module["id"])
            module_label = str(module.get("label", module_id))
            for item in module.get("questions", []):
                question = QuestionBank._to_question(module_id, module_label, item)
                if question.id in questions:
                    raise ValueError(f"Duplicate question id: {question.id}")
                questions[question.id] = question
        return questions

    @staticmethod
    def _to_question(module_id: str, module_label: str, data: dict[str, Any]) -> Question:
        options = [
            Option(
                id=str(opt["id"]),
                text=str(opt["text"]),
                scores={str(k): float(v) for k, v in (opt.get("scores") or {}).items()},
            )
            for opt in data.get("options", [])
        ]
        return Question(
            id=str(data["id"]),
            module_id=module_id,
            module_label=module_label,
            text=str(data["text"]),
            options=options,
        )
