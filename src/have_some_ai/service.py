from __future__ import annotations

from typing import Any

from have_some_ai.models import (
    Answer,
    Assignment,
    DrawnQuestion,
    ObservationEvent,
    Participant,
    ParticipantStatus,
    QueueStatus,
)
from have_some_ai.questionnaire import QuestionBank
from have_some_ai.repository import MealRepository
from have_some_ai.scoring import ScoringEngine


class MealService:
    """Application service for the Have Some "Ai" participant flow."""

    def __init__(
        self,
        repository: MealRepository,
        question_bank: QuestionBank,
        scoring_engine: ScoringEngine,
    ) -> None:
        self._repo = repository
        self._question_bank = question_bank
        self._scoring_engine = scoring_engine

    def create_participant(
        self,
        *,
        notes: str | None = None,
        safety_flags: dict[str, Any] | None = None,
    ) -> Participant:
        return self._repo.create_participant(notes=notes, safety_flags=safety_flags)

    def start_questionnaire(self, participant_id: str) -> list[dict[str, Any]]:
        self._repo.get_participant(participant_id)
        existing = self._repo.get_draws(participant_id)
        if existing:
            return existing

        questions = self._question_bank.draw_questions()
        draws = [
            DrawnQuestion(
                participant_id=participant_id,
                module_id=question.module_id,
                question=question,
            )
            for question in questions
        ]
        self._repo.store_draws(participant_id, draws)
        self._repo.update_participant_status(participant_id, ParticipantStatus.QUESTIONING)
        return self._repo.get_draws(participant_id)

    def submit_answers(self, participant_id: str, answer_items: list[dict[str, str]]) -> None:
        draws = self._repo.get_draws(participant_id)
        if not draws:
            raise ValueError("Questionnaire has not been started")

        valid_question_ids = {draw["question_id"] for draw in draws}
        answers = [
            Answer(
                participant_id=participant_id,
                question_id=str(item["question_id"]),
                option_id=str(item["option_id"]),
            )
            for item in answer_items
        ]

        answered_ids = {answer.question_id for answer in answers}
        unknown = answered_ids - valid_question_ids
        if unknown:
            raise ValueError(f"Answers contain questions that were not drawn: {sorted(unknown)}")

        if len(answered_ids) < len(valid_question_ids):
            missing = sorted(valid_question_ids - answered_ids)
            raise ValueError(f"Missing answers for drawn questions: {missing}")

        self._validate_options(answers)
        self._repo.store_answers(participant_id, answers)
        self._repo.update_participant_status(participant_id, ParticipantStatus.SCORING)

    def add_observations(self, participant_id: str, events: list[dict[str, Any]]) -> None:
        self._repo.get_participant(participant_id)
        observations = [
            ObservationEvent(
                participant_id=participant_id,
                event_type=str(event["event_type"]),
                confidence=float(event.get("confidence", 1.0)),
                duration_ms=event.get("duration_ms"),
                metadata=event.get("metadata") or {},
            )
            for event in events
        ]
        self._repo.store_observation_events(participant_id, observations)

    def assign_food(self, participant_id: str) -> Assignment:
        draws = self._repo.get_draws(participant_id)
        answers = self._repo.get_answers(participant_id)
        if len(answers) < len(draws):
            raise ValueError("Cannot assign food before all drawn questions are answered")

        observations = self._repo.get_observation_events(participant_id)
        assignment = self._scoring_engine.assign(participant_id, answers, observations)
        stored = self._repo.store_assignment(assignment)
        self._repo.update_participant_status(participant_id, ParticipantStatus.ASSIGNED)
        return stored

    def participant_detail(self, participant_id: str) -> dict[str, Any]:
        participant = self._repo.get_participant(participant_id)
        return {
            "participant": participant.__dict__,
            "draws": self._repo.get_draws(participant_id),
            "answers": [answer.__dict__ for answer in self._repo.get_answers(participant_id)],
            "observations": [
                event.__dict__ for event in self._repo.get_observation_events(participant_id)
            ],
            "assignment": _maybe_assignment(self._repo, participant_id),
        }

    def list_participants(self, limit: int = 50) -> list[dict[str, Any]]:
        return [participant.__dict__ for participant in self._repo.list_participants(limit)]

    def list_staff_queue(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._repo.list_staff_queue(limit)

    def update_queue_item(
        self,
        queue_item_id: int,
        status: QueueStatus,
        staff_notes: str | None = None,
    ) -> None:
        self._repo.update_queue_item(queue_item_id, status, staff_notes)

    def export_all(self) -> dict[str, Any]:
        return self._repo.export_all()

    def _validate_options(self, answers: list[Answer]) -> None:
        for answer in answers:
            question = self._question_bank.get_question(answer.question_id)
            valid_options = {option.id for option in question.options}
            if answer.option_id not in valid_options:
                raise ValueError(
                    f"Invalid option {answer.option_id} for question {answer.question_id}"
                )


def _maybe_assignment(repo: MealRepository, participant_id: str) -> dict[str, Any] | None:
    try:
        assignment = repo.get_assignment(participant_id)
    except KeyError:
        return None
    return assignment.__dict__
