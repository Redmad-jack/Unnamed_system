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
    VoiceAnswerInterpretation,
)
from have_some_ai.questionnaire import QuestionBank
from have_some_ai.repository import MealRepository
from have_some_ai.scoring import ScoringEngine
from have_some_ai.voice import RubricInterpreter


class MealService:
    """Application service for the Have Some "Ai" participant flow."""

    def __init__(
        self,
        repository: MealRepository,
        question_bank: QuestionBank,
        scoring_engine: ScoringEngine,
        rubric_interpreter: RubricInterpreter | None = None,
        rubric_confidence_threshold: float = 0.55,
    ) -> None:
        self._repo = repository
        self._question_bank = question_bank
        self._scoring_engine = scoring_engine
        self._rubric_interpreter = rubric_interpreter
        self._rubric_confidence_threshold = rubric_confidence_threshold

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

    def question_speech_text(self, participant_id: str, question_id: str) -> str:
        draws = self._repo.get_draws(participant_id)
        if not draws:
            raise ValueError("Questionnaire has not been started")
        question_index = next(
            (index for index, draw in enumerate(draws) if draw["question_id"] == question_id),
            None,
        )
        if question_index is None:
            raise ValueError(f"Question was not drawn for participant: {question_id}")

        question = self._question_bank.get_question(question_id)
        parts: list[str] = []
        if question_index == 0:
            parts.append("好，那你得先回答我两个问题，我才好分给你吃的。第一个问题。")
        elif question_index == 1:
            parts.append("第二个问题。")

        primary_text = question.text_zh or question.text
        parts.append(primary_text)
        if question.text and question.text != primary_text:
            parts.append(question.text)
        return "\n".join(parts)

    def food_gate_prompt(self, participant_id: str) -> str:
        participant = self._repo.get_participant(participant_id)
        return self._question_bank.food_gate_prompt(participant.public_code)

    def submit_voice_answer(
        self,
        participant_id: str,
        *,
        question_id: str,
        transcript: str,
        detected_language: str | None = None,
        stt_confidence: float | None = None,
        stt_metadata: dict[str, Any] | None = None,
        attempt_id: str | None = None,
    ) -> dict[str, Any]:
        if self._rubric_interpreter is None:
            raise ValueError("Voice rubric interpreter is not configured")

        clean_attempt_id = attempt_id.strip() if attempt_id and attempt_id.strip() else None
        if clean_attempt_id:
            existing = self._repo.get_voice_interpretation_by_attempt(
                participant_id,
                question_id,
                clean_attempt_id,
            )
            if existing is not None:
                return _voice_response(existing)

        if self.get_assignment_if_exists(participant_id) is not None:
            return {
                "status": "already_assigned",
                "question_id": question_id,
                "transcript": transcript.strip(),
                "detected_language": detected_language,
                "option_id": None,
                "confidence": None,
                "reason_zh": "已经完成分配，不再更新答案。",
                "reason_en": "Assignment already exists; voice answer was not updated.",
                "needs_retry": False,
                "interpretation_id": None,
            }

        clean_transcript = transcript.strip()
        self._ensure_drawn_question(participant_id, question_id)

        question = self._question_bank.get_question(question_id)
        metadata = stt_metadata or {}
        if clean_attempt_id:
            metadata = metadata | {"attempt_id": clean_attempt_id}

        if _transcript_is_unclear(clean_transcript):
            interpretation = self._repo.store_voice_interpretation(
                VoiceAnswerInterpretation(
                    participant_id=participant_id,
                    question_id=question_id,
                    attempt_id=clean_attempt_id,
                    transcript=clean_transcript,
                    detected_language=detected_language,
                    stt_confidence=stt_confidence,
                    stt_metadata=metadata,
                    reason_zh="没太听清，请再说一遍。",
                    reason_en="The transcript was empty or too unclear; please try again.",
                    raw_llm_json={"status": "unclear"},
                    status="unclear",
                )
            )
            return _voice_response(interpretation)

        try:
            result = self._rubric_interpreter.interpret(
                question=question,
                transcript=clean_transcript,
                detected_language=detected_language,
            )
            valid_options = {"A", "B"} & {option.id for option in question.options}
            if result.option_id not in valid_options:
                status = "unclear"
                inferred_option_id = None
            elif result.confidence >= self._rubric_confidence_threshold:
                status = "accepted"
                inferred_option_id = result.option_id
            else:
                status = "unclear"
                inferred_option_id = None

            interpretation = self._repo.store_voice_interpretation(
                VoiceAnswerInterpretation(
                    participant_id=participant_id,
                    question_id=question_id,
                    attempt_id=clean_attempt_id,
                    transcript=clean_transcript,
                    detected_language=result.detected_language or detected_language,
                    stt_confidence=stt_confidence,
                    stt_metadata=metadata,
                    inferred_option_id=inferred_option_id,
                    llm_confidence=result.confidence,
                    reason_zh=result.reason_zh or (
                        "没太听清，请再说一遍。" if status == "unclear" else None
                    ),
                    reason_en=result.reason_en or (
                        "The answer was unclear; please try again."
                        if status == "unclear"
                        else None
                    ),
                    raw_llm_json=result.raw_json,
                    status=status,
                )
            )
            if status == "accepted":
                self._repo.store_answers(
                    participant_id,
                    [Answer(participant_id, question_id, inferred_option_id or "")],
                )
                self._repo.update_participant_status(participant_id, ParticipantStatus.SCORING)
            return _voice_response(interpretation)
        except Exception as exc:
            interpretation = self._repo.store_voice_interpretation(
                VoiceAnswerInterpretation(
                    participant_id=participant_id,
                    question_id=question_id,
                    attempt_id=clean_attempt_id,
                    transcript=clean_transcript,
                    detected_language=detected_language,
                    stt_confidence=stt_confidence,
                    stt_metadata=metadata,
                    reason_en=str(exc),
                    status="failed",
                )
            )
            return _voice_response(interpretation)

    def assign_food(self, participant_id: str) -> Assignment:
        existing = self.get_assignment_if_exists(participant_id)
        if existing is not None:
            return existing

        draws = self._repo.get_draws(participant_id)
        answers = self._repo.get_answers(participant_id)
        if len(draws) != 2 or len(answers) != 2:
            raise ValueError("Cannot assign food before the two formal questions are answered")

        observations = self._repo.get_observation_events(participant_id)
        assignment = self._scoring_engine.assign(participant_id, answers, observations)
        stored = self._repo.store_assignment(assignment)
        self._repo.update_participant_status(participant_id, ParticipantStatus.ASSIGNED)
        return stored

    def delete_transient_participant(self, participant_id: str) -> None:
        self._repo.get_participant(participant_id)
        if self._repo.get_answers(participant_id):
            raise ValueError("Cannot delete participant after formal answers are recorded")
        if self.get_assignment_if_exists(participant_id) is not None:
            raise ValueError("Cannot delete participant after assignment")
        self._repo.delete_participant(participant_id)

    def get_assignment_if_exists(self, participant_id: str) -> Assignment | None:
        try:
            return self._repo.get_assignment(participant_id)
        except KeyError:
            return None

    def voice_attempt_response(
        self,
        participant_id: str,
        question_id: str,
        attempt_id: str,
    ) -> dict[str, Any] | None:
        existing = self._repo.get_voice_interpretation_by_attempt(
            participant_id,
            question_id,
            attempt_id,
        )
        return _voice_response(existing) if existing is not None else None

    def participant_detail(self, participant_id: str) -> dict[str, Any]:
        participant = self._repo.get_participant(participant_id)
        return {
            "participant": participant.__dict__,
            "draws": self._repo.get_draws(participant_id),
            "answers": [answer.__dict__ for answer in self._repo.get_answers(participant_id)],
            "observations": [
                event.__dict__ for event in self._repo.get_observation_events(participant_id)
            ],
            "voice_interpretations": [
                item.__dict__ for item in self._repo.get_voice_interpretations(participant_id)
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

    def _ensure_drawn_question(self, participant_id: str, question_id: str) -> None:
        draws = self._repo.get_draws(participant_id)
        if not draws:
            raise ValueError("Questionnaire has not been started")
        drawn_question_ids = {draw["question_id"] for draw in draws}
        if question_id not in drawn_question_ids:
            raise ValueError(f"Question was not drawn for participant: {question_id}")


def _maybe_assignment(repo: MealRepository, participant_id: str) -> dict[str, Any] | None:
    try:
        assignment = repo.get_assignment(participant_id)
    except KeyError:
        return None
    return assignment.__dict__


def _voice_response(interpretation: VoiceAnswerInterpretation) -> dict[str, Any]:
    return {
        "status": interpretation.status,
        "question_id": interpretation.question_id,
        "attempt_id": interpretation.attempt_id,
        "transcript": interpretation.transcript,
        "detected_language": interpretation.detected_language,
        "option_id": interpretation.inferred_option_id,
        "confidence": interpretation.llm_confidence,
        "reason_zh": interpretation.reason_zh,
        "reason_en": interpretation.reason_en,
        "needs_retry": interpretation.status != "accepted",
        "interpretation_id": interpretation.interpretation_id,
    }


def _transcript_is_unclear(transcript: str) -> bool:
    compact = "".join(ch for ch in transcript.strip().lower() if ch.isalnum())
    if not compact:
        return True
    if compact in {"a", "b"}:
        return False
    if len(compact) < 2:
        return True
    unclear_phrases = {
        "c",
        "其他",
        "other",
        "嗯",
        "啊",
        "呃",
        "额",
        "没听清",
        "听不清",
        "听不见",
        "unclear",
        "inaudible",
    }
    return compact in unclear_phrases
