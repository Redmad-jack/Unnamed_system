from __future__ import annotations

import random
from typing import Any, Iterable

from have_some_ai.models import Option, Question


class QuestionBank:
    """Structured question bank with one random draw per configured module."""

    def __init__(self, config: dict[str, Any], rng: random.Random | None = None) -> None:
        self._rng = rng or random.SystemRandom()
        self._modules = config.get("modules", [])
        self._food_gate_openers = [
            str(item).strip()
            for item in config.get("food_gate_openers", [])
            if str(item).strip()
        ]
        self._food_gate_openers_en = [
            str(item).strip()
            for item in config.get("food_gate_openers_en", [])
            if str(item).strip()
        ]
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

    def food_gate_prompt(
        self,
        public_code: str,
        response_language: str | None = None,
    ) -> str:
        if response_language == "en":
            opener = self._food_gate_opener(public_code, language="en")
            if not opener:
                return "Want something to eat?"
            return f"{opener} Want something to eat?"
        opener = self._food_gate_opener(public_code, language="zh")
        return f"{opener}想来点吃的吗？"

    def _food_gate_opener(self, public_code: str, *, language: str) -> str:
        openers = (
            self._food_gate_openers_en
            if language == "en" and self._food_gate_openers_en
            else self._food_gate_openers
        )
        if not openers:
            return ""
        number_text = "".join(ch for ch in public_code if ch.isdigit())
        try:
            participant_number = int(number_text)
        except ValueError:
            participant_number = 1
        index = max(0, participant_number - 1) % len(openers)
        opener = openers[index]
        if opener.endswith(("。", "？", "！", ".", "?", "!")):
            return opener
        return f"{opener}." if language == "en" else f"{opener}。"

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
                text_zh=str(opt["text_zh"]) if opt.get("text_zh") else None,
                scores={str(k): float(v) for k, v in (opt.get("scores") or {}).items()},
            )
            for opt in data.get("options", [])
        ]
        return Question(
            id=str(data["id"]),
            module_id=module_id,
            module_label=module_label,
            text=str(data["text"]),
            text_zh=str(data["text_zh"]) if data.get("text_zh") else None,
            options=options,
        )
