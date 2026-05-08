from __future__ import annotations

from typing import Any

from have_some_ai.chat import ShopkeeperReplyService
from have_some_ai.service import MealService


TOTAL_REQUIRED_QUESTIONS = 2

CHAT_MODE_A_NO_FOOD = "A_NO_FOOD"
CHAT_MODE_B_WANT_FOOD = "B_WANT_FOOD"

FOOD_GATE_WANT = "WANT_FOOD"
FOOD_GATE_NO = "NO_FOOD"
FOOD_GATE_UNCLEAR = "UNCLEAR"

STAGE_FOOD_GATE = "food_gate"
STAGE_FOOD_GATE_CLARIFY = "food_gate_clarify"
STAGE_FREE_CHAT = "free_chat"
STAGE_ASKING_REQUIRED_QUESTION = "asking_required_question"
STAGE_AWAITING_REQUIRED_ANSWER = "awaiting_required_answer"
STAGE_AFTER_REQUIRED_ANSWER = "after_required_answer"
STAGE_FOOD_CHAT_DETOUR = "food_chat_detour"
STAGE_FOOD_CHAT_LIMIT = "food_chat_limit"
STAGE_READY_TO_ASSIGN = "ready_to_assign"
STAGE_ASSIGNED = "assigned"


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
        self._food_gate_unclear_count: dict[str, int] = {}
        self._food_chat_detour_count: dict[str, int] = {}

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

    def prepare_realtime_turn(self, participant_id: str) -> dict[str, Any]:
        """Open or report the current conversation turn for realtime voice."""
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
        if assignment is not None:
            self._clear_live_state(participant_id)
            return self._response(
                stage=STAGE_ASSIGNED,
                participant_status=detail["participant"]["status"],
                answered_count=len(detail["answers"]),
                next_action="none",
                assignment=assignment,
                interpretation=None,
                chat_mode=CHAT_MODE_B_WANT_FOOD,
            )

        chat_mode = self._chat_mode(participant_id, detail)
        if chat_mode == CHAT_MODE_A_NO_FOOD:
            return self._handle_free_chat(participant_id, detail, clean_transcript)

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
                    stage=STAGE_AWAITING_REQUIRED_ANSWER,
                    participant_status=detail["participant"]["status"],
                    answered_count=len(detail["answers"]),
                    current_question=current_question,
                    next_action="submit_required_answer",
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
            stage=STAGE_ASKING_REQUIRED_QUESTION,
            participant_status=detail["participant"]["status"],
            answered_count=len(detail["answers"]),
            current_question=current_question,
            next_action="submit_required_answer",
            last_user_transcript=clean_transcript,
            interpretation=None,
            chat_mode=CHAT_MODE_B_WANT_FOOD,
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
                stage=STAGE_FOOD_GATE,
                participant_status=detail["participant"]["status"],
                answered_count=0,
                next_action="answer_food_gate",
                interpretation=None,
                food_gate_result=None,
                food_gate_prompt=self._service.food_gate_prompt(participant_id),
            )

        result = classify_food_gate(transcript)
        if result == FOOD_GATE_WANT:
            return self._enter_want_food(participant_id, detail, transcript)
        if result == FOOD_GATE_NO:
            return self._enter_no_food(participant_id, detail, transcript, result)

        unclear_count = self._food_gate_unclear_count.get(participant_id, 0) + 1
        self._food_gate_unclear_count[participant_id] = unclear_count
        if unclear_count == 1:
            return self._response(
                stage=STAGE_FOOD_GATE_CLARIFY,
                participant_status=detail["participant"]["status"],
                answered_count=0,
                next_action="answer_food_gate",
                last_user_transcript=transcript,
                interpretation={"status": FOOD_GATE_UNCLEAR},
                food_gate_result=FOOD_GATE_UNCLEAR,
            )
        return self._enter_no_food(participant_id, detail, transcript, FOOD_GATE_UNCLEAR)

    def _handle_free_chat(
        self,
        participant_id: str,
        detail: dict[str, Any],
        transcript: str,
    ) -> dict[str, Any]:
        return self._response(
            stage=STAGE_FREE_CHAT,
            participant_status=detail["participant"]["status"],
            answered_count=len(detail["answers"]),
            next_action="free_chat",
            last_user_transcript=transcript,
            interpretation=None,
            chat_mode=CHAT_MODE_A_NO_FOOD,
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
        return self._response(
            stage=STAGE_FREE_CHAT,
            participant_status=detail["participant"]["status"],
            answered_count=len(detail["answers"]),
            next_action="free_chat",
            last_user_transcript=transcript,
            interpretation={"status": food_gate_result},
            chat_mode=CHAT_MODE_A_NO_FOOD,
            food_gate_result=food_gate_result,
        )

    def _enter_want_food(
        self,
        participant_id: str,
        detail: dict[str, Any],
        transcript: str,
    ) -> dict[str, Any]:
        self._chat_mode_by_participant[participant_id] = CHAT_MODE_B_WANT_FOOD
        self._food_gate_unclear_count.pop(participant_id, None)
        self._food_chat_detour_count[participant_id] = 0
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
            stage=STAGE_ASKING_REQUIRED_QUESTION,
            participant_status=fresh_detail["participant"]["status"],
            answered_count=len(fresh_detail["answers"]),
            current_question=current_question,
            next_action="submit_required_answer",
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
        if _is_continue_ack(transcript):
            self._awaiting_question_by_participant[participant_id] = question_id
            return self._response(
                stage=STAGE_AWAITING_REQUIRED_ANSWER,
                participant_status=detail["participant"]["status"],
                answered_count=len(detail["answers"]),
                current_question=current_question,
                next_action="repeat_current_question",
                last_user_transcript=transcript,
                interpretation={"status": "continue_ack"},
                chat_mode=CHAT_MODE_B_WANT_FOOD,
            )

        metadata = {"source": "conversation_turn"} | (stt_metadata or {})
        voice_result = self._service.submit_voice_answer(
            participant_id,
            question_id=question_id,
            transcript=transcript,
            detected_language=detected_language,
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
            self._food_chat_detour_count[participant_id] = 0
            if answered_count >= len(detail["draws"]):
                return self._assign_and_respond(
                    participant_id,
                    answered_count,
                    interpretation=interpretation,
                )
            return self._response(
                stage=STAGE_AFTER_REQUIRED_ANSWER,
                participant_status=detail["participant"]["status"],
                answered_count=answered_count,
                current_question=_first_unanswered_question(detail),
                next_action="ask_next_required_question",
                last_user_transcript=transcript,
                interpretation_status=voice_result["status"],
                interpretation=interpretation,
                chat_mode=CHAT_MODE_B_WANT_FOOD,
            )

        current_question = _draw_by_question_id(detail["draws"], question_id)
        self._awaiting_question_by_participant[participant_id] = question_id
        if _is_food_chat_detour(transcript, voice_result):
            return self._food_chat_detour_response(
                participant_id,
                detail,
                current_question,
                transcript,
                voice_result,
            )
        return self._response(
            stage=STAGE_AWAITING_REQUIRED_ANSWER,
            participant_status=detail["participant"]["status"],
            answered_count=answered_count,
            current_question=current_question,
            next_action="repeat_current_question",
            last_user_transcript=transcript,
            interpretation_status=voice_result["status"],
            interpretation={"status": "unclear"},
            chat_mode=CHAT_MODE_B_WANT_FOOD,
        )

    def _food_chat_detour_response(
        self,
        participant_id: str,
        detail: dict[str, Any],
        current_question: dict[str, Any],
        transcript: str,
        voice_result: dict[str, Any],
    ) -> dict[str, Any]:
        count = self._food_chat_detour_count.get(participant_id, 0) + 1
        self._food_chat_detour_count[participant_id] = count
        stage = STAGE_FOOD_CHAT_DETOUR if count < 3 else STAGE_FOOD_CHAT_LIMIT
        return self._response(
            stage=stage,
            participant_status=detail["participant"]["status"],
            answered_count=len(detail["answers"]),
            current_question=current_question,
            next_action="repeat_current_question",
            last_user_transcript=transcript,
            interpretation_status=voice_result["status"],
            interpretation={"status": "detour", "count": count},
            chat_mode=CHAT_MODE_B_WANT_FOOD,
            food_chat_detour_count=count,
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
            stage=STAGE_READY_TO_ASSIGN,
            participant_status=STAGE_ASSIGNED,
            answered_count=answered_count,
            next_action="assign",
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

    def _clear_live_state(self, participant_id: str) -> None:
        self._awaiting_question_by_participant.pop(participant_id, None)
        self._food_gate_unclear_count.pop(participant_id, None)
        self._food_chat_detour_count.pop(participant_id, None)

    def _response(
        self,
        *,
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
        food_chat_detour_count: int | None = None,
    ) -> dict[str, Any]:
        current_question_text = (
            _question_text(current_question) if current_question is not None else None
        )
        context = {
            "stage": stage,
            "participant_status": participant_status,
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
            "food_chat_detour_count": food_chat_detour_count,
        }
        reply = self._reply_service.generate_reply(context)
        return {
            "reply_text": reply["reply_text"],
            "stage": stage,
            "chat_mode": chat_mode,
            "food_gate_result": food_gate_result,
            "food_chat_detour_count": food_chat_detour_count,
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


def classify_food_gate(transcript: str) -> str:
    compact = _compact(transcript)
    if not compact:
        return FOOD_GATE_UNCLEAR
    no_tokens = {
        "不吃",
        "不想吃",
        "不要",
        "不用",
        "先不",
        "算了",
        "不饿",
        "不需要",
        "不了",
        "no",
        "nope",
        "notnow",
        "notreally",
        "dontwant",
        "donotwant",
    }
    if any(token in compact for token in no_tokens):
        return FOOD_GATE_NO
    want_tokens = {
        "想吃",
        "要吃",
        "来点",
        "吃的",
        "吃",
        "要",
        "想",
        "可以",
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
    if any(token in compact for token in want_tokens):
        return FOOD_GATE_WANT
    return FOOD_GATE_UNCLEAR


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


def _question_text(draw: dict[str, Any]) -> str:
    return str(draw.get("question_text_zh") or draw["question_text"])


def _interpretation_from_voice_result(voice_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "accepted",
        "choice": voice_result["option_id"],
        "confidence": voice_result["confidence"],
    }


def _is_continue_ack(transcript: str) -> bool:
    compact = _compact(transcript)
    return compact in {
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


def _is_food_chat_detour(transcript: str, voice_result: dict[str, Any]) -> bool:
    if voice_result.get("status") == "accepted":
        return False
    compact = _compact(transcript)
    if not compact or _is_continue_ack(transcript):
        return False
    non_detour_unclear = {
        "不知道",
        "不确定",
        "可能吧",
        "随便",
        "没听清",
        "听不清",
        "听不见",
        "再说一遍",
        "不懂",
        "不明白",
        "unclear",
        "idontknow",
        "notsure",
    }
    if any(token in compact for token in non_detour_unclear):
        return False
    detour_tokens = {
        "你呢",
        "你觉得",
        "为什么",
        "什么",
        "怎么",
        "哪",
        "哈哈",
        "笑",
        "开玩笑",
        "聊天",
        "聊",
        "天气",
        "项目",
        "老板",
        "店主",
        "ai",
        "人工智能",
        "whatis",
        "why",
        "how",
        "joke",
        "haha",
    }
    return (
        "?" in transcript
        or "？" in transcript
        or any(token in compact for token in detour_tokens)
        or len(compact) >= 8
    )


def _compact(text: str) -> str:
    return "".join(ch for ch in text.strip().lower() if ch.isalnum())
