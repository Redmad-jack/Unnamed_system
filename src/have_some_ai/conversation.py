from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from have_some_ai.chat import ShopkeeperReplyService
from have_some_ai.service import MealService


TOTAL_REQUIRED_QUESTIONS = 2

CHAT_MODE_A_NO_FOOD = "A_NO_FOOD"
CHAT_MODE_B_WANT_FOOD = "B_WANT_FOOD"

FOOD_GATE_WANT = "WANT_FOOD"
FOOD_GATE_NO = "NO_FOOD"
FOOD_GATE_UNCLEAR = "UNCLEAR"

RESPONSE_LANGUAGE_EN = "en"
RESPONSE_LANGUAGE_ZH = "zh"

STAGE_LANGUAGE_GATE = "language_gate"
STAGE_FOOD_GATE = "food_gate"
STAGE_NOT_EATING_CHAT = "not_eating_chat"
STAGE_FORMAL_QUESTION_1 = "formal_question_1"
STAGE_FORMAL_QUESTION_2 = "formal_question_2"
STAGE_FAREWELL = "farewell"
STAGE_ASSIGNED = "assigned"
STAGE_DONE = "done"

ROUTE_WANT_FOOD = "want_food"
ROUTE_NO_FOOD = "no_food"
ROUTE_CHITCHAT = "chitchat"
ROUTE_UNCLEAR_SPEECH = "unclear_speech"
ROUTE_ANSWER_ATTEMPT = "answer_attempt"
ROUTE_SYSTEM_COMMAND = "system_command"
ROUTE_NOISE = "noise"
ROUTE_LANGUAGE = "language"

MAX_NOT_EATING_CHAT_TURNS = 3
MAX_FORMAL_CHITCHAT_TURNS = 3


@dataclass(frozen=True)
class TurnRoute:
    route: str
    command: str | None = None


class ConversationOrchestrator:
    """Shopkeeper conversation state machine.

    Food-gate chat and detours never write meal_answers. Only accepted A/B
    interpretations for the two formal questions enter scoring.
    """

    def __init__(
        self,
        service: MealService,
        reply_service: ShopkeeperReplyService | None = None,
    ) -> None:
        self._service = service
        self._reply_service = reply_service or ShopkeeperReplyService()
        self._awaiting_question_by_participant: dict[str, str] = {}
        self._chat_mode_by_participant: dict[str, str] = {}
        self._food_gate_prompted: set[str] = set()
        self._response_language_by_participant: dict[str, str] = {}
        self._food_gate_chitchat_count: dict[str, int] = {}
        self._not_eating_chat_count: dict[str, int] = {}
        self._formal_chitchat_count: dict[str, int] = {}
        self._language_router = LanguageGateRouter()
        self._food_gate_router = FoodGateRouter()
        self._formal_turn_router = FormalTurnRouter()

    def conversation_turn(
        self,
        participant_id: str,
        transcript: str,
        *,
        detected_language: str | None = None,
        stt_confidence: float | None = None,
        stt_metadata: dict[str, Any] | None = None,
        attempt_id: str | None = None,
    ) -> dict[str, Any]:
        return self.handle_turn(
            participant_id,
            transcript,
            detected_language=detected_language,
            stt_confidence=stt_confidence,
            stt_metadata=stt_metadata,
            attempt_id=attempt_id,
        )

    def prepare_stream_turn(self, participant_id: str) -> dict[str, Any]:
        """Open or report the current conversation turn for streaming voice."""
        return self.handle_turn(participant_id, "")

    def handle_turn(
        self,
        participant_id: str,
        transcript: str,
        *,
        detected_language: str | None = None,
        stt_confidence: float | None = None,
        stt_metadata: dict[str, Any] | None = None,
        attempt_id: str | None = None,
    ) -> dict[str, Any]:
        detail = self._service.participant_detail(participant_id)
        clean_transcript = transcript.strip()

        assignment = detail["assignment"]
        response_language = self._response_language(participant_id, detail)
        if assignment is not None:
            self._clear_live_state(participant_id)
            return self._response(
                participant_id=participant_id,
                stage=STAGE_ASSIGNED,
                participant_status=detail["participant"]["status"],
                answered_count=len(detail["answers"]),
                next_action="none",
                assignment=assignment,
                interpretation=None,
                chat_mode=CHAT_MODE_B_WANT_FOOD,
            )

        if response_language is None:
            return self._handle_language_gate(participant_id, detail, clean_transcript)

        chat_mode = self._chat_mode(participant_id, detail)
        if chat_mode == CHAT_MODE_A_NO_FOOD:
            return self._handle_not_eating_chat(participant_id, detail, clean_transcript)

        if not detail["draws"] and chat_mode != CHAT_MODE_B_WANT_FOOD:
            return self._handle_food_gate(participant_id, detail, clean_transcript)

        if chat_mode == CHAT_MODE_B_WANT_FOOD and not detail["draws"]:
            return self._enter_want_food(participant_id, detail, clean_transcript)

        if len(detail["answers"]) >= len(detail["draws"]):
            return self._assign_and_respond(participant_id, len(detail["answers"]))

        awaiting_question_id = self._awaiting_question_id(participant_id, detail)
        if awaiting_question_id is not None:
            current_question = _draw_by_question_id(detail["draws"], awaiting_question_id)
            if not clean_transcript:
                return self._response(
                    participant_id=participant_id,
                    stage=_formal_stage(len(detail["answers"])),
                    participant_status=detail["participant"]["status"],
                    answered_count=len(detail["answers"]),
                    current_question=current_question,
                    next_action="answer_formal_question",
                    last_user_transcript=clean_transcript,
                    interpretation=None,
                    chat_mode=CHAT_MODE_B_WANT_FOOD,
                )
            return self._handle_required_answer(
                participant_id,
                awaiting_question_id,
                clean_transcript,
                detected_language=detected_language,
                stt_confidence=stt_confidence,
                stt_metadata=stt_metadata,
                attempt_id=attempt_id,
            )

        current_question = _first_unanswered_question(detail)
        if current_question is None:
            return self._assign_and_respond(participant_id, len(detail["answers"]))

        self._awaiting_question_by_participant[participant_id] = (
            current_question["question_id"]
        )
        return self._response(
            participant_id=participant_id,
            stage=_formal_stage(len(detail["answers"])),
            participant_status=detail["participant"]["status"],
            answered_count=len(detail["answers"]),
            current_question=current_question,
            next_action="answer_formal_question",
            last_user_transcript=clean_transcript,
            interpretation=None,
            chat_mode=CHAT_MODE_B_WANT_FOOD,
        )

    def _handle_language_gate(
        self,
        participant_id: str,
        detail: dict[str, Any],
        transcript: str,
    ) -> dict[str, Any]:
        routed = self._language_router.route(transcript)
        if routed.route == ROUTE_LANGUAGE and routed.command in {
            RESPONSE_LANGUAGE_EN,
            RESPONSE_LANGUAGE_ZH,
        }:
            self._response_language_by_participant[participant_id] = routed.command
            return self._handle_food_gate(participant_id, detail, "")

        interpretation = None
        if transcript:
            interpretation = {"route": "unclear_language"}
        return self._response(
            participant_id=participant_id,
            stage=STAGE_LANGUAGE_GATE,
            participant_status=detail["participant"]["status"],
            answered_count=0,
            next_action="choose_language",
            last_user_transcript=transcript,
            interpretation=interpretation,
            response_language=None,
        )

    def _handle_food_gate(
        self,
        participant_id: str,
        detail: dict[str, Any],
        transcript: str,
    ) -> dict[str, Any]:
        if participant_id not in self._food_gate_prompted:
            self._food_gate_prompted.add(participant_id)
            return self._response(
                participant_id=participant_id,
                stage=STAGE_FOOD_GATE,
                participant_status=detail["participant"]["status"],
                answered_count=0,
                next_action="answer_food_gate",
                interpretation=None,
                food_gate_result=None,
                food_gate_prompt=self._service.food_gate_prompt(
                    participant_id,
                    response_language=self._response_language_by_participant.get(
                        participant_id
                    ),
                ),
            )

        routed = self._food_gate_router.route(transcript)
        if routed.route == ROUTE_WANT_FOOD:
            return self._enter_want_food(participant_id, detail, transcript)
        if routed.route in {ROUTE_NO_FOOD, ROUTE_SYSTEM_COMMAND} and routed.command == "cancel":
            return self._enter_no_food(participant_id, detail, transcript, FOOD_GATE_NO)
        if routed.route == ROUTE_NO_FOOD:
            return self._enter_no_food(participant_id, detail, transcript, FOOD_GATE_NO)

        if routed.route in {ROUTE_UNCLEAR_SPEECH, ROUTE_NOISE}:
            return self._response(
                participant_id=participant_id,
                stage=STAGE_FOOD_GATE,
                participant_status=detail["participant"]["status"],
                answered_count=0,
                next_action="answer_food_gate",
                last_user_transcript=transcript,
                interpretation={"route": routed.route},
                food_gate_result=FOOD_GATE_UNCLEAR,
                food_gate_prompt=self._service.food_gate_prompt(
                    participant_id,
                    response_language=self._response_language_by_participant.get(
                        participant_id
                    ),
                ),
            )

        count = self._food_gate_chitchat_count.get(participant_id, 0) + 1
        self._food_gate_chitchat_count[participant_id] = count
        return self._response(
            participant_id=participant_id,
            stage=STAGE_FOOD_GATE,
            participant_status=detail["participant"]["status"],
            answered_count=0,
            next_action="answer_food_gate",
            last_user_transcript=transcript,
            interpretation={"route": ROUTE_CHITCHAT, "count": count},
            food_gate_prompt=self._service.food_gate_prompt(
                participant_id,
                response_language=self._response_language_by_participant.get(
                    participant_id
                ),
            ),
        )

    def _handle_not_eating_chat(
        self,
        participant_id: str,
        detail: dict[str, Any],
        transcript: str,
    ) -> dict[str, Any]:
        if not transcript:
            return self._response(
                participant_id=participant_id,
                stage=STAGE_NOT_EATING_CHAT,
                participant_status=detail["participant"]["status"],
                answered_count=len(detail["answers"]),
                next_action="not_eating_chat",
                last_user_transcript=transcript,
                interpretation=None,
                chat_mode=CHAT_MODE_A_NO_FOOD,
                not_eating_chat_count=self._not_eating_chat_count.get(participant_id, 0),
            )

        count = self._not_eating_chat_count.get(participant_id, 0) + 1
        self._not_eating_chat_count[participant_id] = count
        if count >= MAX_NOT_EATING_CHAT_TURNS:
            self._clear_live_state(participant_id)
            self._service.delete_transient_participant(participant_id)
            return self._response(
                participant_id=participant_id,
                stage=STAGE_DONE,
                participant_status="deleted",
                answered_count=len(detail["answers"]),
                next_action="end_session",
                last_user_transcript=transcript,
                interpretation={"route": ROUTE_CHITCHAT, "count": count},
                chat_mode=CHAT_MODE_A_NO_FOOD,
                not_eating_chat_count=count,
                participant_deleted=True,
            )
        return self._response(
            participant_id=participant_id,
            stage=STAGE_NOT_EATING_CHAT,
            participant_status=detail["participant"]["status"],
            answered_count=len(detail["answers"]),
            next_action="not_eating_chat",
            last_user_transcript=transcript,
            interpretation={"route": ROUTE_CHITCHAT, "count": count},
            chat_mode=CHAT_MODE_A_NO_FOOD,
            not_eating_chat_count=count,
        )

    def _enter_no_food(
        self,
        participant_id: str,
        detail: dict[str, Any],
        transcript: str,
        food_gate_result: str,
    ) -> dict[str, Any]:
        self._chat_mode_by_participant[participant_id] = CHAT_MODE_A_NO_FOOD
        self._awaiting_question_by_participant.pop(participant_id, None)
        self._not_eating_chat_count[participant_id] = 0
        return self._response(
            participant_id=participant_id,
            stage=STAGE_NOT_EATING_CHAT,
            participant_status=detail["participant"]["status"],
            answered_count=len(detail["answers"]),
            next_action="not_eating_chat",
            last_user_transcript=transcript,
            interpretation={"status": food_gate_result},
            chat_mode=CHAT_MODE_A_NO_FOOD,
            food_gate_result=food_gate_result,
            not_eating_chat_count=0,
        )

    def _enter_want_food(
        self,
        participant_id: str,
        detail: dict[str, Any],
        transcript: str,
    ) -> dict[str, Any]:
        self._chat_mode_by_participant[participant_id] = CHAT_MODE_B_WANT_FOOD
        self._food_gate_chitchat_count.pop(participant_id, None)
        self._not_eating_chat_count.pop(participant_id, None)
        self._formal_chitchat_count[participant_id] = 0
        if not detail["draws"]:
            self._service.start_questionnaire(participant_id)
        fresh_detail = self._service.participant_detail(participant_id)
        current_question = _first_unanswered_question(fresh_detail)
        if current_question is None:
            return self._assign_and_respond(participant_id, len(fresh_detail["answers"]))
        self._awaiting_question_by_participant[participant_id] = (
            current_question["question_id"]
        )
        return self._response(
            participant_id=participant_id,
            stage=_formal_stage(len(fresh_detail["answers"])),
            participant_status=fresh_detail["participant"]["status"],
            answered_count=len(fresh_detail["answers"]),
            current_question=current_question,
            next_action="answer_formal_question",
            last_user_transcript=transcript,
            interpretation={"status": FOOD_GATE_WANT},
            chat_mode=CHAT_MODE_B_WANT_FOOD,
            food_gate_result=FOOD_GATE_WANT,
        )

    def _handle_required_answer(
        self,
        participant_id: str,
        question_id: str,
        transcript: str,
        *,
        detected_language: str | None = None,
        stt_confidence: float | None = None,
        stt_metadata: dict[str, Any] | None = None,
        attempt_id: str | None = None,
    ) -> dict[str, Any]:
        detail = self._service.participant_detail(participant_id)
        current_question = _draw_by_question_id(detail["draws"], question_id)
        routed = self._formal_turn_router.route(transcript, current_question)
        if routed.route == ROUTE_SYSTEM_COMMAND and routed.command == "repeat":
            self._awaiting_question_by_participant[participant_id] = question_id
            return self._response(
                participant_id=participant_id,
                stage=_formal_stage(len(detail["answers"])),
                participant_status=detail["participant"]["status"],
                answered_count=len(detail["answers"]),
                current_question=current_question,
                next_action="repeat_current_question",
                last_user_transcript=transcript,
                interpretation={"route": ROUTE_SYSTEM_COMMAND, "command": "repeat"},
                chat_mode=CHAT_MODE_B_WANT_FOOD,
            )

        if routed.route == ROUTE_SYSTEM_COMMAND and routed.command == "cancel":
            self._clear_live_state(participant_id)
            return self._response(
                participant_id=participant_id,
                stage=STAGE_DONE,
                participant_status=detail["participant"]["status"],
                answered_count=len(detail["answers"]),
                current_question=current_question,
                next_action="end_session",
                last_user_transcript=transcript,
                interpretation={"route": ROUTE_SYSTEM_COMMAND, "command": "cancel"},
                chat_mode=CHAT_MODE_B_WANT_FOOD,
            )

        if routed.route in {ROUTE_UNCLEAR_SPEECH, ROUTE_NOISE}:
            self._awaiting_question_by_participant[participant_id] = question_id
            return self._response(
                participant_id=participant_id,
                stage=_formal_stage(len(detail["answers"])),
                participant_status=detail["participant"]["status"],
                answered_count=len(detail["answers"]),
                current_question=current_question,
                next_action="repeat_current_question",
                last_user_transcript=transcript,
                interpretation={"route": routed.route},
                chat_mode=CHAT_MODE_B_WANT_FOOD,
            )

        if routed.route == ROUTE_CHITCHAT:
            return self._formal_chitchat_response(
                participant_id,
                detail,
                current_question,
                transcript,
            )

        metadata = {"source": "conversation_turn"} | (stt_metadata or {})
        voice_result = self._service.submit_voice_answer(
            participant_id,
            question_id=question_id,
            transcript=transcript,
            detected_language=detected_language
            or self._response_language_by_participant.get(participant_id),
            stt_confidence=stt_confidence,
            stt_metadata=metadata,
            attempt_id=attempt_id,
        )
        return self._conversation_response_after_voice_result(
            participant_id,
            question_id,
            transcript,
            voice_result,
        )

    def _conversation_response_after_voice_result(
        self,
        participant_id: str,
        question_id: str,
        transcript: str,
        voice_result: dict[str, Any],
    ) -> dict[str, Any]:
        detail = self._service.participant_detail(participant_id)
        answered_count = len(detail["answers"])

        if voice_result["status"] == "accepted":
            interpretation = _interpretation_from_voice_result(voice_result)
            self._awaiting_question_by_participant.pop(participant_id, None)
            self._formal_chitchat_count[participant_id] = 0
            if answered_count >= len(detail["draws"]):
                return self._assign_and_respond(
                    participant_id,
                    answered_count,
                    interpretation=interpretation,
                )
            next_question = _first_unanswered_question(detail)
            if next_question is not None:
                self._awaiting_question_by_participant[participant_id] = next_question[
                    "question_id"
                ]
            return self._response(
                participant_id=participant_id,
                stage=_formal_stage(answered_count),
                participant_status=detail["participant"]["status"],
                answered_count=answered_count,
                current_question=next_question,
                next_action="answer_formal_question",
                last_user_transcript=transcript,
                interpretation_status=voice_result["status"],
                interpretation=interpretation,
                chat_mode=CHAT_MODE_B_WANT_FOOD,
            )

        current_question = _draw_by_question_id(detail["draws"], question_id)
        self._awaiting_question_by_participant[participant_id] = question_id
        return self._response(
            participant_id=participant_id,
            stage=_formal_stage(answered_count),
            participant_status=detail["participant"]["status"],
            answered_count=answered_count,
            current_question=current_question,
            next_action="repeat_current_question",
            last_user_transcript=transcript,
            interpretation_status=voice_result["status"],
            interpretation={"status": "unclear", "source": "judge"},
            chat_mode=CHAT_MODE_B_WANT_FOOD,
        )

    def _formal_chitchat_response(
        self,
        participant_id: str,
        detail: dict[str, Any],
        current_question: dict[str, Any],
        transcript: str,
    ) -> dict[str, Any]:
        count = self._formal_chitchat_count.get(participant_id, 0) + 1
        self._formal_chitchat_count[participant_id] = count
        return self._response(
            participant_id=participant_id,
            stage=_formal_stage(len(detail["answers"])),
            participant_status=detail["participant"]["status"],
            answered_count=len(detail["answers"]),
            current_question=current_question,
            next_action="repeat_current_question",
            last_user_transcript=transcript,
            interpretation={"route": ROUTE_CHITCHAT, "count": count},
            chat_mode=CHAT_MODE_B_WANT_FOOD,
            formal_chitchat_count=count,
        )

    def _assign_and_respond(
        self,
        participant_id: str,
        answered_count: int,
        interpretation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assignment = self._service.assign_food(participant_id)
        self._clear_live_state(participant_id)
        self._chat_mode_by_participant[participant_id] = CHAT_MODE_B_WANT_FOOD
        return self._response(
            participant_id=participant_id,
            stage=STAGE_FAREWELL,
            participant_status=STAGE_ASSIGNED,
            answered_count=answered_count,
            next_action="end_session",
            assignment=assignment.__dict__,
            interpretation=interpretation,
            chat_mode=CHAT_MODE_B_WANT_FOOD,
        )

    def _awaiting_question_id(
        self,
        participant_id: str,
        detail: dict[str, Any],
    ) -> str | None:
        question_id = self._awaiting_question_by_participant.get(participant_id)
        if question_id is None:
            return None
        unanswered_ids = {
            draw["question_id"]
            for draw in detail["draws"]
        } - {
            answer["question_id"]
            for answer in detail["answers"]
        }
        if question_id not in unanswered_ids:
            self._awaiting_question_by_participant.pop(participant_id, None)
            return None
        return question_id

    def _chat_mode(self, participant_id: str, detail: dict[str, Any]) -> str | None:
        explicit = self._chat_mode_by_participant.get(participant_id)
        if explicit is not None:
            return explicit
        if detail["draws"] or detail["answers"] or detail["assignment"] is not None:
            self._chat_mode_by_participant[participant_id] = CHAT_MODE_B_WANT_FOOD
            return CHAT_MODE_B_WANT_FOOD
        return None

    def _response_language(
        self,
        participant_id: str,
        detail: dict[str, Any],
    ) -> str | None:
        explicit = self._response_language_by_participant.get(participant_id)
        if explicit is not None:
            return explicit
        if (
            detail["draws"]
            or detail["answers"]
            or detail["assignment"] is not None
            or self._chat_mode_by_participant.get(participant_id) is not None
        ):
            self._response_language_by_participant[participant_id] = RESPONSE_LANGUAGE_ZH
            return RESPONSE_LANGUAGE_ZH
        return None

    def _clear_live_state(self, participant_id: str) -> None:
        self._awaiting_question_by_participant.pop(participant_id, None)
        self._chat_mode_by_participant.pop(participant_id, None)
        self._food_gate_chitchat_count.pop(participant_id, None)
        self._not_eating_chat_count.pop(participant_id, None)
        self._formal_chitchat_count.pop(participant_id, None)

    def _response(
        self,
        *,
        participant_id: str,
        stage: str,
        participant_status: str,
        answered_count: int,
        next_action: str,
        current_question: dict[str, Any] | None = None,
        assignment: dict[str, Any] | None = None,
        last_user_transcript: str | None = None,
        interpretation_status: str | None = None,
        interpretation: dict[str, Any] | None = None,
        chat_mode: str | None = None,
        food_gate_result: str | None = None,
        food_gate_prompt: str | None = None,
        not_eating_chat_count: int | None = None,
        formal_chitchat_count: int | None = None,
        participant_deleted: bool = False,
        response_language: str | None = None,
    ) -> dict[str, Any]:
        resolved_language = (
            response_language
            if response_language is not None
            else self._response_language_by_participant.get(participant_id)
        )
        if resolved_language is None and stage != STAGE_LANGUAGE_GATE:
            resolved_language = RESPONSE_LANGUAGE_ZH
        current_question_text = (
            _question_text(current_question, resolved_language)
            if current_question is not None
            else None
        )
        context = {
            "stage": stage,
            "participant_status": participant_status,
            "next_action": next_action,
            "answered_count": answered_count,
            "total_questions": TOTAL_REQUIRED_QUESTIONS,
            "current_question_text": current_question_text,
            "last_user_transcript": last_user_transcript,
            "interpretation_status": interpretation_status,
            "interpretation": interpretation,
            "assignment": assignment,
            "chat_mode": chat_mode,
            "food_gate_result": food_gate_result,
            "food_gate_prompt": food_gate_prompt,
            "not_eating_chat_count": not_eating_chat_count,
            "formal_chitchat_count": formal_chitchat_count,
            "participant_deleted": participant_deleted,
            "response_language": resolved_language,
        }
        reply = self._reply_service.generate_reply(context)
        return {
            "reply_text": reply["reply_text"],
            "stage": stage,
            "chat_mode": chat_mode,
            "food_gate_result": food_gate_result,
            "not_eating_chat_count": not_eating_chat_count,
            "formal_chitchat_count": formal_chitchat_count,
            "participant_deleted": participant_deleted,
            "response_language": resolved_language,
            "answered_count": answered_count,
            "total_questions": TOTAL_REQUIRED_QUESTIONS,
            "current_question_id": (
                current_question["question_id"] if current_question is not None else None
            ),
            "current_question_text": current_question_text,
            "next_action": next_action,
            "interpretation": interpretation,
            "assignment": assignment,
        }


class LanguageGateRouter:
    """Choose response language without entering the scored question flow."""

    def route(self, transcript: str) -> TurnRoute:
        compact = _compact(transcript)
        if not compact:
            return TurnRoute(ROUTE_NOISE)
        if compact in {"e", "en"} or any(
            token in compact for token in {"english", "英文"}
        ):
            return TurnRoute(ROUTE_LANGUAGE, RESPONSE_LANGUAGE_EN)
        if compact in {"c", "zh"} or any(
            token in compact for token in {"chinese", "中文", "汉语", "漢語"}
        ):
            return TurnRoute(ROUTE_LANGUAGE, RESPONSE_LANGUAGE_ZH)
        if _is_unclear_speech(compact):
            return TurnRoute(ROUTE_UNCLEAR_SPEECH)
        if _has_cjk_text(transcript):
            return TurnRoute(ROUTE_LANGUAGE, RESPONSE_LANGUAGE_ZH)
        if _has_clear_latin_text(compact):
            return TurnRoute(ROUTE_LANGUAGE, RESPONSE_LANGUAGE_EN)
        return TurnRoute(ROUTE_UNCLEAR_SPEECH)


class FoodGateRouter:
    """Classify food-gate utterances before any scoring flow exists."""

    def route(self, transcript: str) -> TurnRoute:
        compact = _compact(transcript)
        if _is_noise(compact):
            return TurnRoute(ROUTE_NOISE)
        if _is_unclear_speech(compact):
            return TurnRoute(ROUTE_UNCLEAR_SPEECH)
        command = _system_command(compact)
        if command == "cancel":
            return TurnRoute(ROUTE_SYSTEM_COMMAND, command)
        if _matches_any(compact, _FOOD_GATE_NO_TOKENS):
            return TurnRoute(ROUTE_NO_FOOD)
        if _matches_any(compact, _FOOD_GATE_WANT_TOKENS):
            return TurnRoute(ROUTE_WANT_FOOD)
        return TurnRoute(ROUTE_CHITCHAT)


class FormalTurnRouter:
    """Route formal-question turns before Claude A/B judging."""

    def route(self, transcript: str, current_question: dict[str, Any]) -> TurnRoute:
        compact = _compact(transcript)
        if _is_noise(compact):
            return TurnRoute(ROUTE_NOISE)
        if _is_unclear_speech(compact):
            return TurnRoute(ROUTE_UNCLEAR_SPEECH)
        command = _system_command(compact)
        if command is not None:
            return TurnRoute(ROUTE_SYSTEM_COMMAND, command)
        if _has_choice_marker(transcript, compact):
            return TurnRoute(ROUTE_ANSWER_ATTEMPT)
        if compact in _FORMAL_NONANSWER_ACK_TOKENS:
            return TurnRoute(ROUTE_CHITCHAT)
        if _looks_like_side_chat(transcript, compact):
            return TurnRoute(ROUTE_CHITCHAT)
        if _looks_like_option_semantics(compact, current_question):
            return TurnRoute(ROUTE_ANSWER_ATTEMPT)
        if _matches_any(compact, _FORMAL_UNCLEAR_ANSWER_TOKENS):
            return TurnRoute(ROUTE_ANSWER_ATTEMPT)
        if _looks_like_unrelated_formal_chitchat(transcript, compact, current_question):
            return TurnRoute(ROUTE_CHITCHAT)
        return TurnRoute(ROUTE_ANSWER_ATTEMPT)


_FOOD_GATE_NO_TOKENS = {
    "不吃",
    "不想吃",
    "不要",
    "不用",
    "先不",
    "先不了",
    "算了",
    "不饿",
    "不需要",
    "不了",
    "只是看看",
    "看看",
    "路过",
    "no",
    "nope",
    "notnow",
    "notreally",
    "dontwant",
    "donotwant",
}

_FOOD_GATE_WANT_TOKENS = {
    "想吃",
    "要吃",
    "来点",
    "吃的",
    "吃",
    "要",
    "想试试",
    "试试",
    "参加",
    "可以",
    "来吧",
    "好",
    "行",
    "yes",
    "yeah",
    "yep",
    "ok",
    "okay",
    "sure",
    "please",
    "want",
    "hungry",
}

_UNCLEAR_SPEECH_TOKENS = {
    "嗯",
    "啊",
    "呃",
    "额",
    "呃呃",
    "嗯嗯",
    "唔",
    "呜",
    "em",
    "um",
    "uh",
    "er",
}

_REPEAT_COMMAND_TOKENS = {
    "重复",
    "再说一遍",
    "再讲一遍",
    "没听清",
    "听不清",
    "听不见",
    "repeat",
    "again",
}

_CANCEL_COMMAND_TOKENS = {
    "停止",
    "取消",
    "结束",
    "不玩了",
    "算了",
    "stop",
    "cancel",
    "quit",
}

_SIDE_CHAT_TOKENS = {
    "你是谁",
    "你是",
    "你呢",
    "你觉得",
    "你会",
    "你能",
    "这个摊位",
    "摊位",
    "装置",
    "作品",
    "项目",
    "好好玩",
    "好玩",
    "今天有点累",
    "有点累",
    "好累",
    "累",
    "天气",
    "老板",
    "店主",
    "聊天",
    "聊聊",
    "开玩笑",
    "哈哈",
    "笑",
    "whatisthis",
    "whoareyou",
    "installation",
    "project",
    "booth",
    "tired",
    "fun",
    "haha",
}

_OFF_TOPIC_CONTEXT_TOKENS = {
    "今天",
    "刚才",
    "刚刚",
    "朋友",
    "同学",
    "学校",
    "上班",
    "工作",
    "天气",
    "下雨",
    "雨",
    "外面",
    "旁边",
    "声音",
    "机器",
    "机器人",
    "摊位",
    "项目",
    "作品",
    "展览",
    "装置",
    "路上",
    "吃饭",
    "喝水",
    "衣服",
    "today",
    "yesterday",
    "tomorrow",
    "friend",
    "school",
    "work",
    "weather",
    "rain",
    "outside",
    "nearby",
    "voice",
    "sound",
    "machine",
    "robot",
    "project",
    "booth",
    "installation",
    "exhibition",
}

_QUESTION_RELATED_TOKEN_CANDIDATES = {
    "ai",
    "answer",
    "apologized",
    "angry",
    "analyze",
    "beside",
    "bedroom",
    "closed",
    "confides",
    "difference",
    "door",
    "idea",
    "loneliness",
    "meant",
    "open",
    "opinion",
    "physically",
    "repeated",
    "sad",
    "sadder",
    "sleep",
    "thank",
    "troubles",
    "understand",
    "understood",
    "不必要",
    "倾诉",
    "关着",
    "关门",
    "分析",
    "卧室",
    "原谅",
    "孤独",
    "开着",
    "开门",
    "想法",
    "感谢",
    "懂",
    "歉",
    "生气",
    "真正",
    "睡觉",
    "观点",
    "说过",
    "谢谢",
    "身边",
    "道歉",
    "门",
    "难过",
}

_LATIN_STOP_WORDS = {
    "about",
    "after",
    "and",
    "are",
    "but",
    "can",
    "did",
    "does",
    "ever",
    "for",
    "from",
    "has",
    "have",
    "having",
    "kind",
    "one",
    "someone",
    "something",
    "that",
    "the",
    "their",
    "them",
    "then",
    "they",
    "this",
    "when",
    "which",
    "with",
    "you",
    "your",
}

_FORMAL_UNCLEAR_ANSWER_TOKENS = {
    "随便",
    "都行",
    "都可以",
    "都像",
    "都不像",
    "不确定",
    "不知道",
    "可能吧",
    "选c",
    "c",
    "other",
    "notsure",
    "idontknow",
}

_FORMAL_NONANSWER_ACK_TOKENS = {
    "好",
    "好吧",
    "好的",
    "行",
    "行吧",
    "可以",
    "可以吧",
    "ok",
    "okay",
    "sure",
    "fine",
}


def _formal_stage(answered_count: int) -> str:
    return STAGE_FORMAL_QUESTION_1 if answered_count <= 0 else STAGE_FORMAL_QUESTION_2


def _matches_any(compact: str, tokens: set[str]) -> bool:
    return any(token in compact for token in tokens)


def _is_noise(compact: str) -> bool:
    return not compact


def _is_unclear_speech(compact: str) -> bool:
    if not compact:
        return False
    if compact in {"a", "b", "c"}:
        return False
    if compact in _UNCLEAR_SPEECH_TOKENS:
        return True
    return len(compact) < 2


def _system_command(compact: str) -> str | None:
    if _matches_any(compact, _REPEAT_COMMAND_TOKENS):
        return "repeat"
    if _matches_any(compact, _CANCEL_COMMAND_TOKENS):
        return "cancel"
    return None


def _has_choice_marker(transcript: str, compact: str) -> bool:
    upper = transcript.upper()
    if "选A" in upper or "选B" in upper or "选C" in upper:
        return True
    if compact in {"a", "b", "c"}:
        return True
    return any(
        token in compact
        for token in {"选a", "选b", "选c", "答案a", "答案b", "答案c", "aa", "bb"}
    )


def _looks_like_side_chat(transcript: str, compact: str) -> bool:
    if _matches_any(compact, _SIDE_CHAT_TOKENS):
        return True
    if ("?" in transcript or "？" in transcript) and any(
        token in compact for token in {"你", "这个", "什么", "为什么", "怎么", "who", "what", "why", "how"}
    ):
        return True
    return False


def _looks_like_unrelated_formal_chitchat(
    transcript: str,
    compact: str,
    current_question: dict[str, Any],
) -> bool:
    if not _has_substantive_formal_content(transcript):
        return False
    if _has_choice_marker(transcript, compact):
        return False
    if _is_related_to_current_question(compact, current_question):
        return False
    return _matches_any(compact, _OFF_TOPIC_CONTEXT_TOKENS) or _has_side_question_shape(
        transcript,
        compact,
    )


def _has_side_question_shape(transcript: str, compact: str) -> bool:
    if "?" not in transcript and "？" not in transcript:
        return False
    return any(
        token in compact
        for token in {"你", "这个", "什么", "为什么", "怎么", "who", "what", "why", "how"}
    )


def _has_substantive_formal_content(transcript: str) -> bool:
    if sum(1 for ch in transcript if "\u4e00" <= ch <= "\u9fff") >= 4:
        return True
    return len(_latin_words(transcript)) >= 3


def _is_related_to_current_question(
    compact: str,
    current_question: dict[str, Any],
) -> bool:
    return any(
        token and token in compact
        for token in _question_related_tokens(current_question)
    )


def _question_related_tokens(current_question: dict[str, Any]) -> set[str]:
    source_text = _formal_question_source_text(current_question)
    compact_source = _compact(source_text)
    tokens = {
        token
        for token in _QUESTION_RELATED_TOKEN_CANDIDATES
        if token in compact_source
    }
    tokens.update(_latin_words(source_text))
    return tokens


def _formal_question_source_text(current_question: dict[str, Any]) -> str:
    parts = [
        str(current_question.get("question_text") or ""),
        str(current_question.get("question_text_zh") or ""),
    ]
    for option in current_question.get("options") or []:
        parts.append(str(option.get("text") or ""))
        parts.append(str(option.get("text_zh") or ""))
    return " ".join(parts)


def _latin_words(text: str) -> list[str]:
    words: list[str] = []
    current: list[str] = []
    for ch in text.lower():
        if "a" <= ch <= "z":
            current.append(ch)
            continue
        if current:
            word = "".join(current)
            if len(word) >= 3 and word not in _LATIN_STOP_WORDS:
                words.append(word)
            current = []
    if current:
        word = "".join(current)
        if len(word) >= 3 and word not in _LATIN_STOP_WORDS:
            words.append(word)
    return words


def _looks_like_option_semantics(compact: str, current_question: dict[str, Any]) -> bool:
    options = current_question.get("options") or []
    option_text = "".join(
        _compact(str(option.get("text", "")) + str(option.get("text_zh", "")))
        for option in options
    )
    semantic_tokens = {
        "有",
        "没有",
        "是",
        "不是",
        "开着",
        "关着",
        "打开",
        "关上",
        "open",
        "closed",
        "yes",
        "no",
    }
    if compact in semantic_tokens:
        return True
    return any(token and token in compact for token in _option_keywords(option_text))


def _option_keywords(option_text: str) -> set[str]:
    return {
        token
        for token in {
            "open",
            "closed",
            "yes",
            "no",
            "有",
            "没有",
            "开着",
            "关着",
            "理解",
            "分析",
            "难过",
            "生气",
            "道歉",
            "谢谢",
            "ai",
        }
        if token in option_text
    }


def _first_unanswered_question(detail: dict[str, Any]) -> dict[str, Any] | None:
    answered_question_ids = {
        answer["question_id"]
        for answer in detail["answers"]
    }
    for draw in detail["draws"]:
        if draw["question_id"] not in answered_question_ids:
            return draw
    return None


def _draw_by_question_id(draws: list[dict[str, Any]], question_id: str) -> dict[str, Any]:
    for draw in draws:
        if draw["question_id"] == question_id:
            return draw
    raise ValueError(f"Question was not drawn for participant: {question_id}")


def _question_text(draw: dict[str, Any], response_language: str | None) -> str:
    if response_language == RESPONSE_LANGUAGE_EN:
        return str(draw["question_text"])
    return str(draw.get("question_text_zh") or draw["question_text"])


def _interpretation_from_voice_result(voice_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "accepted",
        "choice": voice_result["option_id"],
        "confidence": voice_result["confidence"],
    }


def _compact(text: str) -> str:
    return "".join(ch for ch in text.strip().lower() if ch.isalnum())


def _has_cjk_text(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _has_clear_latin_text(compact: str) -> bool:
    latin_count = sum(1 for ch in compact if "a" <= ch <= "z")
    return latin_count >= 2
