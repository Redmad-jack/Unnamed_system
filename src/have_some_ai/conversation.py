from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from have_some_ai.chat import ShopkeeperReplyService
from have_some_ai.service import MealService
from have_some_ai.voice import FoodGateIntentInterpreter


TOTAL_REQUIRED_QUESTIONS = 2

CHAT_MODE_A_NO_FOOD = "A_NO_FOOD"
CHAT_MODE_B_WANT_FOOD = "B_WANT_FOOD"
CHAT_MODE_C_TALK_ONLY = "TALK_ONLY"

FOOD_GATE_WANT = "WANT_FOOD"
FOOD_GATE_NO = "NO_FOOD"
FOOD_GATE_CHAT = "WANT_CHAT"
FOOD_GATE_UNCLEAR = "UNCLEAR"

RESPONSE_LANGUAGE_EN = "en"
RESPONSE_LANGUAGE_ZH = "zh"

STAGE_LANGUAGE_GATE = "language_gate"
STAGE_FOOD_GATE = "food_gate"
STAGE_NOT_EATING_CHAT = "not_eating_chat"
STAGE_TALK_ONLY_CHAT = "talk_only_chat"
STAGE_FORMAL_QUESTION_1 = "formal_question_1"
STAGE_FORMAL_QUESTION_2 = "formal_question_2"
STAGE_POST_ASSIGNMENT_CHAT = "post_assignment_chat"
STAGE_FAREWELL = "farewell"
STAGE_ASSIGNED = "assigned"
STAGE_DONE = "done"

ROUTE_WANT_FOOD = "want_food"
ROUTE_WANT_CHAT = "want_chat"
ROUTE_NO_FOOD = "no_food"
ROUTE_CHITCHAT = "chitchat"
ROUTE_UNCLEAR_SPEECH = "unclear_speech"
ROUTE_ANSWER_ATTEMPT = "answer_attempt"
ROUTE_SYSTEM_COMMAND = "system_command"
ROUTE_NOISE = "noise"
ROUTE_LANGUAGE = "language"
ROUTE_COMMAND_REPLY_NOW = "reply_now"

MAX_NOT_EATING_CHAT_TURNS = 3
MAX_TALK_ONLY_CHAT_TURNS = 3
MAX_FORMAL_CHITCHAT_TURNS = 3
MAX_POST_ASSIGNMENT_CHAT_TURNS = 2


@dataclass(frozen=True)
class TurnRoute:
    route: str
    command: str | None = None


@dataclass(frozen=True)
class FoodGateEvidence:
    strong_food: bool
    weak_food: bool
    no_food: bool
    wants_chat: bool


class ConversationOrchestrator:
    """Shopkeeper conversation state machine.

    Food-gate chat and detours never write meal_answers. Only accepted A/B
    interpretations for the two formal questions enter scoring.
    """

    def __init__(
        self,
        service: MealService,
        reply_service: ShopkeeperReplyService | None = None,
        food_gate_interpreter: FoodGateIntentInterpreter | None = None,
    ) -> None:
        self._service = service
        self._reply_service = reply_service or ShopkeeperReplyService()
        self._food_gate_interpreter = food_gate_interpreter
        self._awaiting_question_by_participant: dict[str, str] = {}
        self._chat_mode_by_participant: dict[str, str] = {}
        self._food_gate_prompted: set[str] = set()
        self._response_language_by_participant: dict[str, str] = {}
        self._food_gate_chitchat_count: dict[str, int] = {}
        self._not_eating_chat_count: dict[str, int] = {}
        self._talk_only_chat_count: dict[str, int] = {}
        self._formal_chitchat_count: dict[str, int] = {}
        self._post_assignment_chat_count: dict[str, int] = {}
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
            if participant_id in self._post_assignment_chat_count:
                return self._handle_post_assignment_chat(
                    participant_id,
                    detail,
                    clean_transcript,
                    assignment,
                )
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
                participant_public_code=_participant_public_code(detail),
            )

        if response_language is None:
            return self._handle_language_gate(participant_id, detail, clean_transcript)

        chat_mode = self._chat_mode(participant_id, detail)
        if chat_mode == CHAT_MODE_A_NO_FOOD:
            return self._handle_not_eating_chat(participant_id, detail, clean_transcript)
        if chat_mode == CHAT_MODE_C_TALK_ONLY:
            return self._handle_talk_only_chat(participant_id, detail, clean_transcript)

        if not detail["draws"] and chat_mode != CHAT_MODE_B_WANT_FOOD:
            return self._handle_food_gate(participant_id, detail, clean_transcript)

        if chat_mode == CHAT_MODE_B_WANT_FOOD and not detail["draws"]:
            return self._enter_want_food(participant_id, detail, clean_transcript)

        if len(detail["answers"]) >= len(detail["draws"]):
            return self._assign_and_respond(
                participant_id,
                len(detail["answers"]),
                participant_public_code=_participant_public_code(detail),
            )

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
            return self._assign_and_respond(
                participant_id,
                len(detail["answers"]),
                participant_public_code=_participant_public_code(detail),
            )

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
        routed = self._route_food_gate_with_llm(participant_id, transcript, routed)
        if routed.route == ROUTE_WANT_FOOD:
            return self._enter_want_food(participant_id, detail, transcript)
        if routed.route == ROUTE_WANT_CHAT:
            return self._enter_talk_only(
                participant_id,
                detail,
                transcript,
                reply_now=routed.command == ROUTE_COMMAND_REPLY_NOW,
            )
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

    def _route_food_gate_with_llm(
        self,
        participant_id: str,
        transcript: str,
        fallback_route: TurnRoute,
    ) -> TurnRoute:
        if self._food_gate_interpreter is None:
            return fallback_route
        if not _should_consult_food_gate_llm(transcript, fallback_route):
            return fallback_route

        response_language = self._response_language_by_participant.get(participant_id)
        try:
            interpreted = self._food_gate_interpreter.interpret_food_gate(
                food_gate_prompt=self._service.food_gate_prompt(
                    participant_id,
                    response_language=response_language,
                ),
                transcript=transcript,
                response_language=response_language,
                local_fallback_route=fallback_route.route,
            )
        except Exception:
            return fallback_route
        if interpreted is None:
            return fallback_route
        return TurnRoute(interpreted.route)

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

    def _handle_talk_only_chat(
        self,
        participant_id: str,
        detail: dict[str, Any],
        transcript: str,
    ) -> dict[str, Any]:
        if not transcript:
            return self._response(
                participant_id=participant_id,
                stage=STAGE_TALK_ONLY_CHAT,
                participant_status=detail["participant"]["status"],
                answered_count=len(detail["answers"]),
                next_action="talk_only_chat",
                last_user_transcript=transcript,
                interpretation=None,
                chat_mode=CHAT_MODE_C_TALK_ONLY,
                food_gate_result=FOOD_GATE_CHAT,
                talk_only_chat_count=self._talk_only_chat_count.get(participant_id, 0),
            )

        count = self._talk_only_chat_count.get(participant_id, 0) + 1
        self._talk_only_chat_count[participant_id] = count
        if count >= MAX_TALK_ONLY_CHAT_TURNS:
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
                chat_mode=CHAT_MODE_C_TALK_ONLY,
                food_gate_result=FOOD_GATE_CHAT,
                talk_only_chat_count=count,
                participant_deleted=True,
            )
        return self._response(
            participant_id=participant_id,
            stage=STAGE_TALK_ONLY_CHAT,
            participant_status=detail["participant"]["status"],
            answered_count=len(detail["answers"]),
            next_action="talk_only_chat",
            last_user_transcript=transcript,
            interpretation={"route": ROUTE_CHITCHAT, "count": count},
            chat_mode=CHAT_MODE_C_TALK_ONLY,
            food_gate_result=FOOD_GATE_CHAT,
            talk_only_chat_count=count,
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

    def _enter_talk_only(
        self,
        participant_id: str,
        detail: dict[str, Any],
        transcript: str,
        *,
        reply_now: bool = False,
    ) -> dict[str, Any]:
        self._chat_mode_by_participant[participant_id] = CHAT_MODE_C_TALK_ONLY
        self._awaiting_question_by_participant.pop(participant_id, None)
        self._food_gate_chitchat_count.pop(participant_id, None)
        self._not_eating_chat_count.pop(participant_id, None)
        initial_count = 1 if reply_now and transcript else 0
        self._talk_only_chat_count[participant_id] = initial_count
        interpretation = (
            {"route": ROUTE_CHITCHAT, "count": initial_count}
            if initial_count
            else {"status": FOOD_GATE_CHAT}
        )
        return self._response(
            participant_id=participant_id,
            stage=STAGE_TALK_ONLY_CHAT,
            participant_status=detail["participant"]["status"],
            answered_count=len(detail["answers"]),
            next_action="talk_only_chat",
            last_user_transcript=transcript,
            interpretation=interpretation,
            chat_mode=CHAT_MODE_C_TALK_ONLY,
            food_gate_result=FOOD_GATE_CHAT,
            talk_only_chat_count=initial_count,
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
            return self._assign_and_respond(
                participant_id,
                len(fresh_detail["answers"]),
                participant_public_code=_participant_public_code(fresh_detail),
            )
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

        if voice_result["status"] == "chitchat":
            current_question = _draw_by_question_id(detail["draws"], question_id)
            self._awaiting_question_by_participant[participant_id] = question_id
            return self._formal_chitchat_response(
                participant_id,
                detail,
                current_question,
                transcript,
            )

        if voice_result["status"] == "accepted":
            interpretation = _interpretation_from_voice_result(voice_result)
            self._awaiting_question_by_participant.pop(participant_id, None)
            self._formal_chitchat_count[participant_id] = 0
            if answered_count >= len(detail["draws"]):
                return self._assign_and_respond(
                    participant_id,
                    answered_count,
                    interpretation=interpretation,
                    participant_public_code=_participant_public_code(detail),
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

    def _handle_post_assignment_chat(
        self,
        participant_id: str,
        detail: dict[str, Any],
        transcript: str,
        assignment: dict[str, Any],
    ) -> dict[str, Any]:
        if not transcript:
            return self._response(
                participant_id=participant_id,
                stage=STAGE_POST_ASSIGNMENT_CHAT,
                participant_status=detail["participant"]["status"],
                answered_count=len(detail["answers"]),
                next_action="post_assignment_chat",
                last_user_transcript=transcript,
                assignment=assignment,
                interpretation=None,
                chat_mode=CHAT_MODE_B_WANT_FOOD,
                post_assignment_chat_count=self._post_assignment_chat_count.get(
                    participant_id,
                    0,
                ),
                participant_public_code=_participant_public_code(detail),
            )

        count = self._post_assignment_chat_count.get(participant_id, 0) + 1
        self._post_assignment_chat_count[participant_id] = count
        if count > MAX_POST_ASSIGNMENT_CHAT_TURNS:
            self._clear_live_state(participant_id)
            return self._response(
                participant_id=participant_id,
                stage=STAGE_DONE,
                participant_status=detail["participant"]["status"],
                answered_count=len(detail["answers"]),
                next_action="end_session",
                last_user_transcript=transcript,
                assignment=assignment,
                interpretation={"route": ROUTE_CHITCHAT, "count": count},
                chat_mode=CHAT_MODE_B_WANT_FOOD,
                post_assignment_chat_count=count,
                participant_public_code=_participant_public_code(detail),
            )
        return self._response(
            participant_id=participant_id,
            stage=STAGE_POST_ASSIGNMENT_CHAT,
            participant_status=detail["participant"]["status"],
            answered_count=len(detail["answers"]),
            next_action="post_assignment_chat",
            last_user_transcript=transcript,
            assignment=assignment,
            interpretation={"route": ROUTE_CHITCHAT, "count": count},
            chat_mode=CHAT_MODE_B_WANT_FOOD,
            post_assignment_chat_count=count,
            participant_public_code=_participant_public_code(detail),
        )

    def _assign_and_respond(
        self,
        participant_id: str,
        answered_count: int,
        interpretation: dict[str, Any] | None = None,
        participant_public_code: str | None = None,
    ) -> dict[str, Any]:
        assignment = self._service.assign_food(participant_id)
        self._clear_live_state(participant_id)
        self._chat_mode_by_participant[participant_id] = CHAT_MODE_B_WANT_FOOD
        self._post_assignment_chat_count[participant_id] = 0
        return self._response(
            participant_id=participant_id,
            stage=STAGE_POST_ASSIGNMENT_CHAT,
            participant_status=STAGE_ASSIGNED,
            answered_count=answered_count,
            next_action="post_assignment_chat",
            assignment=assignment.__dict__,
            interpretation=interpretation,
            chat_mode=CHAT_MODE_B_WANT_FOOD,
            post_assignment_chat_count=0,
            participant_public_code=participant_public_code,
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
        self._talk_only_chat_count.pop(participant_id, None)
        self._formal_chitchat_count.pop(participant_id, None)
        self._post_assignment_chat_count.pop(participant_id, None)

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
        talk_only_chat_count: int | None = None,
        formal_chitchat_count: int | None = None,
        post_assignment_chat_count: int | None = None,
        participant_deleted: bool = False,
        response_language: str | None = None,
        participant_public_code: str | None = None,
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
            "talk_only_chat_count": talk_only_chat_count,
            "formal_chitchat_count": formal_chitchat_count,
            "post_assignment_chat_count": post_assignment_chat_count,
            "participant_deleted": participant_deleted,
            "response_language": resolved_language,
            "participant_public_code": participant_public_code,
        }
        reply = self._reply_service.generate_reply(context)
        return {
            "reply_text": reply["reply_text"],
            "stage": stage,
            "chat_mode": chat_mode,
            "food_gate_result": food_gate_result,
            "not_eating_chat_count": not_eating_chat_count,
            "talk_only_chat_count": talk_only_chat_count,
            "formal_chitchat_count": formal_chitchat_count,
            "post_assignment_chat_count": post_assignment_chat_count,
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
        command = _system_command(compact)
        if command == "cancel":
            return TurnRoute(ROUTE_SYSTEM_COMMAND, command)
        if _is_food_gate_explanation_question(compact):
            return TurnRoute(ROUTE_WANT_CHAT, ROUTE_COMMAND_REPLY_NOW)
        evidence = _food_gate_evidence(compact)
        if evidence.no_food and evidence.wants_chat:
            return TurnRoute(ROUTE_WANT_CHAT)
        if evidence.no_food:
            return TurnRoute(ROUTE_NO_FOOD)
        if evidence.strong_food:
            return TurnRoute(ROUTE_WANT_FOOD)
        if evidence.wants_chat:
            return TurnRoute(ROUTE_WANT_CHAT)
        if evidence.weak_food:
            return TurnRoute(ROUTE_WANT_FOOD)
        if _is_unclear_speech(compact):
            return TurnRoute(ROUTE_UNCLEAR_SPEECH)
        return TurnRoute(ROUTE_WANT_CHAT)


class FormalTurnRouter:
    """Route formal-question turns before Claude A/B judging."""

    def route(self, transcript: str, current_question: dict[str, Any]) -> TurnRoute:
        compact = _compact(transcript)
        if _is_noise(compact):
            return TurnRoute(ROUTE_NOISE)
        command = _system_command(compact)
        if command is not None:
            return TurnRoute(ROUTE_SYSTEM_COMMAND, command)
        if _is_unclear_speech(compact):
            return TurnRoute(ROUTE_UNCLEAR_SPEECH)
        return TurnRoute(ROUTE_ANSWER_ATTEMPT)


_FOOD_GATE_NO_EXACT_TOKENS = {
    "不要",
    "不用",
    "先不",
    "先不了",
    "算了",
    "不了",
    "不需要",
    "看看",
    "no",
    "nope",
    "notnow",
    "notreally",
    "dontwant",
    "donotwant",
}

_FOOD_GATE_NO_PHRASE_TOKENS = {
    "不吃",
    "不想吃",
    "不要吃",
    "先不吃",
    "不饿",
    "不用吃",
    "不用了",
    "不需要吃",
    "不需要了",
    "不参加",
    "不想参加",
    "只是看看",
    "路过",
    "nofood",
    "nothanks",
    "nothungry",
    "noneedfood",
    "noneedtoeat",
    "dontneedfood",
    "dontneedtoeat",
    "dontwantfood",
    "dontwanttoeat",
    "donotneedfood",
    "donotneedtoeat",
    "donotwantfood",
    "donotwanttoeat",
    "idontneedfood",
    "idontneedtoeat",
    "idonotneedfood",
    "idonotneedtoeat",
}

_FOOD_GATE_STRONG_WANT_EXACT_TOKENS = {
    "吃",
    "吃点",
    "吃饭",
    "好吃",
    "干饭",
    "恰饭",
    "开饭",
    "饿了",
    "eat",
    "food",
    "meal",
    "snack",
    "hungry",
}

_FOOD_GATE_WEAK_WANT_EXACT_TOKENS = {
    "要",
    "好",
    "行",
    "可以",
    "来吧",
    "yes",
    "yeah",
    "yep",
    "ok",
    "okay",
    "sure",
    "please",
    "want",
}

_FOOD_GATE_STRONG_WANT_PHRASE_TOKENS = {
    "想吃",
    "要吃",
    "来点吃",
    "来点饭",
    "来口",
    "来份",
    "来一份",
    "整点吃",
    "整点饭",
    "点吃的",
    "搞点吃",
    "搞点饭",
    "弄点吃",
    "弄点饭",
    "给我来点",
    "给我来份",
    "给我来一份",
    "给我来口",
    "给我来碗",
    "给我来杯",
    "吃的",
    "吃东西",
    "吃一点",
    "吃点东西",
    "干饭",
    "恰饭",
    "开饭",
    "饿",
    "尝尝",
    "尝一下",
    "尝一口",
    "wantfood",
    "wantsomethingtoeat",
    "iwanttoeat",
    "iwantfood",
    "iwouldliketoeat",
    "iwouldlikefood",
    "somethingtoeat",
    "getfood",
    "hungry",
}

_FOOD_GATE_WEAK_WANT_PHRASE_TOKENS = {
    "想试试",
    "试试",
    "参加",
}

_FOOD_GATE_CHAT_TOKENS = {
    "我们说说话吧",
    "那我们说说话吧",
    "那说说话吧",
    "说说话吧",
    "说说吧",
    "聊聊天吧",
    "我们聊聊天吧",
    "那聊聊天吧",
    "聊一下吧",
    "聊一会儿吧",
    "想聊天",
    "我想聊天",
    "我想和你聊天",
    "我想和你说话",
    "我想和你说说话",
    "和你说说话",
    "跟你说说话",
    "跟你聊聊",
    "和你聊聊",
    "先聊聊",
    "先说说话",
    "不吃聊聊吧",
    "不想吃想聊聊",
    "不饿聊会儿",
    "只是想聊聊天",
    "就想说说话",
    "可以聊天吗",
    "能和你聊聊吗",
    "陪我聊会儿",
    "先不吃聊一下",
    "想问你点事",
    "想问你问题",
    "想知道你是谁",
    "你是谁",
    "你想聊什么",
    "随便聊聊",
    "说话",
    "聊天",
    "聊",
    "talk",
    "chat",
    "letstalk",
    "letustalk",
    "canwetalk",
    "iwanttotalk",
    "justtalk",
}

_FOOD_GATE_EXPLANATION_QUESTION_TOKENS = {
    "为什么",
    "为啥",
    "为何",
    "怎么",
    "什么意思",
    "什么意义",
    "代表什么",
    "是什么意思",
    "why",
    "whatdoes",
    "whatdo",
}

_FOOD_GATE_EXPLANATION_SUBJECT_TOKENS = {
    "ai",
    "食物",
    "吃的",
    "吃东西",
    "做吃",
    "做饭",
    "做菜",
    "做汤",
    "做沙拉",
    "下厨",
    "厨房",
    "羹汤",
    "汤",
    "沙拉",
    "艾苗",
    "艾草",
    "aimiao",
    "mugwort",
    "food",
    "eat",
    "serving",
    "serve",
    "cooking",
    "cook",
    "kitchen",
    "soup",
    "salad",
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

def _formal_stage(answered_count: int) -> str:
    return STAGE_FORMAL_QUESTION_1 if answered_count <= 0 else STAGE_FORMAL_QUESTION_2


def _matches_any(compact: str, tokens: set[str]) -> bool:
    return any(token in compact for token in tokens)


def _food_gate_evidence(compact: str) -> FoodGateEvidence:
    return FoodGateEvidence(
        strong_food=_matches_food_gate_strong_want(compact),
        weak_food=_matches_food_gate_weak_want(compact),
        no_food=_matches_food_gate_no(compact),
        wants_chat=_matches_any(compact, _FOOD_GATE_CHAT_TOKENS),
    )


def _should_consult_food_gate_llm(transcript: str, fallback_route: TurnRoute) -> bool:
    compact = _compact(transcript)
    if not compact:
        return False
    if fallback_route.command == ROUTE_COMMAND_REPLY_NOW:
        return False
    if fallback_route.route in {
        ROUTE_NOISE,
        ROUTE_UNCLEAR_SPEECH,
        ROUTE_SYSTEM_COMMAND,
        ROUTE_NO_FOOD,
    }:
        return False

    evidence = _food_gate_evidence(compact)
    if evidence.no_food or evidence.wants_chat:
        return False
    if fallback_route.route == ROUTE_WANT_FOOD:
        return evidence.weak_food and not evidence.strong_food
    if fallback_route.route == ROUTE_WANT_CHAT:
        return True
    return False


def _is_food_gate_explanation_question(compact: str) -> bool:
    if not compact:
        return False
    has_question = _matches_any(compact, _FOOD_GATE_EXPLANATION_QUESTION_TOKENS)
    if not has_question:
        return False
    return _matches_any(compact, _FOOD_GATE_EXPLANATION_SUBJECT_TOKENS)


def _matches_food_gate_no(compact: str) -> bool:
    return (
        compact in _FOOD_GATE_NO_EXACT_TOKENS
        or any(token in compact for token in _FOOD_GATE_NO_PHRASE_TOKENS)
    )


def _matches_food_gate_strong_want(compact: str) -> bool:
    return (
        compact in _FOOD_GATE_STRONG_WANT_EXACT_TOKENS
        or any(token in compact for token in _FOOD_GATE_STRONG_WANT_PHRASE_TOKENS)
    )


def _matches_food_gate_weak_want(compact: str) -> bool:
    return (
        compact in _FOOD_GATE_WEAK_WANT_EXACT_TOKENS
        or any(token in compact for token in _FOOD_GATE_WEAK_WANT_PHRASE_TOKENS)
    )


def _is_noise(compact: str) -> bool:
    return not compact


def _is_unclear_speech(compact: str) -> bool:
    if not compact:
        return False
    if compact in {"a", "b", "c", "有", "是", "好", "行", "要", "吃", "聊"}:
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


def _participant_public_code(detail: dict[str, Any]) -> str | None:
    participant = detail.get("participant")
    if not isinstance(participant, dict):
        return None
    public_code = participant.get("public_code")
    if public_code is None:
        return None
    text = str(public_code).strip()
    return text or None


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
