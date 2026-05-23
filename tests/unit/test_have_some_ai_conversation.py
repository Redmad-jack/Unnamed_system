from __future__ import annotations

import random
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from have_some_ai.config import load_have_some_ai_config
from have_some_ai.conversation import (
    CHAT_MODE_A_NO_FOOD,
    CHAT_MODE_B_WANT_FOOD,
    CHAT_MODE_C_TALK_ONLY,
    ConversationOrchestrator,
)
from have_some_ai.db import run_migrations
from have_some_ai.interfaces.api import app
from have_some_ai.questionnaire import QuestionBank
from have_some_ai.repository import MealRepository
from have_some_ai.scoring import ScoringEngine
from have_some_ai.service import MealService
from have_some_ai.voice import FoodGateIntentInterpretation, RubricInterpretation


class FixedReplyService:
    def generate_reply(self, _context):
        return {"reply_text": "店主说话归店主，流程归流程。"}


class FakeRubricInterpreter:
    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def interpret(self, **kwargs):
        self.calls.append(kwargs)
        return self._results.pop(0)


class FakeFoodGateIntentInterpreter:
    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def interpret_food_gate(self, **kwargs):
        self.calls.append(kwargs)
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class CountingScoringEngine(ScoringEngine):
    def __init__(self, scoring_config, question_bank):
        super().__init__(scoring_config, question_bank)
        self.calls = 0

    def assign(self, *args, **kwargs):
        self.calls += 1
        return super().assign(*args, **kwargs)


def test_new_participant_first_turn_asks_language_gate_without_draws():
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()

        result = orchestrator.handle_turn(participant.id, "")
        detail = service.participant_detail(participant.id)

        assert result["stage"] == "language_gate"
        assert result["next_action"] == "choose_language"
        assert result["total_questions"] == 2
        assert result["current_question_id"] is None
        assert result["assignment"] is None
        assert "Hi. 你好～ Do you want to talk in 中文 or English?" in result["reply_text"]
        assert len(detail["draws"]) == 0
        assert len(detail["answers"]) == 0
    finally:
        conn.close()


def test_language_gate_infers_english_before_food_gate_without_draws():
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()
        orchestrator.handle_turn(participant.id, "")

        result = orchestrator.handle_turn(participant.id, "I would like something to eat")
        detail = service.participant_detail(participant.id)

        assert result["stage"] == "food_gate"
        assert result["response_language"] == "en"
        assert result["next_action"] == "answer_food_gate"
        assert result["answered_count"] == 0
        assert result["total_questions"] == 2
        assert result["current_question_id"] is None
        assert result["reply_text"] == service.food_gate_prompt(
            participant.id,
            response_language="en",
        )
        assert result["reply_text"] == (
            "Your outfit looks pretty good today. I might buy some tonight and "
            "make my staff wear them on shift. Do you want something to eat, or do you want to talk?"
        )
        assert detail["draws"] == []
        assert detail["answers"] == []
    finally:
        conn.close()


def test_language_gate_infers_chinese_before_food_gate_without_draws():
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()
        orchestrator.handle_turn(participant.id, "")

        result = orchestrator.handle_turn(participant.id, "我想吃")
        detail = service.participant_detail(participant.id)

        assert result["stage"] == "food_gate"
        assert result["response_language"] == "zh"
        assert result["next_action"] == "answer_food_gate"
        assert result["answered_count"] == 0
        assert detail["draws"] == []
        assert detail["answers"] == []
    finally:
        conn.close()


def test_language_gate_reprompts_unclear_language_without_drawing_questions():
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()

        result = orchestrator.handle_turn(participant.id, "嗯")
        detail = service.participant_detail(participant.id)

        assert result["stage"] == "language_gate"
        assert result["next_action"] == "choose_language"
        assert result["interpretation"] == {"route": "unclear_language"}
        assert detail["draws"] == []
        assert detail["answers"] == []
    finally:
        conn.close()


def test_no_food_enters_not_eating_chat_and_never_draws_questions():
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()
        _enter_food_gate(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, "先不吃了")
        detail = service.participant_detail(participant.id)

        assert result["stage"] == "not_eating_chat"
        assert result["chat_mode"] == CHAT_MODE_A_NO_FOOD
        assert result["food_gate_result"] == "NO_FOOD"
        assert result["next_action"] == "not_eating_chat"
        assert result["assignment"] is None
        assert detail["draws"] == []
        assert detail["answers"] == []
    finally:
        conn.close()


def test_food_gate_chat_question_enters_talk_only_and_does_not_default_to_no_food():
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()
        _enter_food_gate(orchestrator, participant.id)

        unclear = orchestrator.handle_turn(participant.id, "嗯")
        chitchat = orchestrator.handle_turn(participant.id, "你是谁啊")

        assert unclear["stage"] == "food_gate"
        assert unclear["interpretation"] == {"route": "unclear_speech"}
        assert chitchat["stage"] == "talk_only_chat"
        assert chitchat["interpretation"] == {"status": "WANT_CHAT"}
        assert chitchat["next_action"] == "talk_only_chat"
        assert chitchat["chat_mode"] == CHAT_MODE_C_TALK_ONLY
        assert service.participant_detail(participant.id)["draws"] == []
    finally:
        conn.close()


@pytest.mark.parametrize(
    "transcript",
    [
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
        "不吃，聊聊吧",
        "不想吃，想聊聊",
        "我不饿，聊会儿",
        "我只是想聊聊天",
        "我就想说说话",
        "可以聊天吗",
        "能和你聊聊吗",
        "你陪我聊会儿",
        "我们先不吃，聊一下",
        "我想问你点事",
        "我想问你问题",
        "我想知道你是谁",
        "你是谁啊",
        "你想聊什么",
        "随便聊聊",
        "说话",
        "聊天",
        "聊",
        "talk",
        "chat",
        "let's talk",
        "let us talk",
        "can we talk",
        "I want to talk",
        "just talk",
    ],
)
def test_food_gate_chat_intents_enter_talk_only_chat(transcript):
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()
        _enter_food_gate(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, transcript)
        detail = service.participant_detail(participant.id)

        assert result["stage"] == "talk_only_chat"
        assert result["chat_mode"] == CHAT_MODE_C_TALK_ONLY
        assert result["food_gate_result"] == "WANT_CHAT"
        assert result["next_action"] == "talk_only_chat"
        assert result["talk_only_chat_count"] == 0
        assert detail["draws"] == []
        assert detail["answers"] == []
        assert result["assignment"] is None
    finally:
        conn.close()


@pytest.mark.parametrize(
    "transcript",
    [
        "我今天刚从学校过来，外面还在下雨",
        "这个地方有点奇怪",
        "你要不要先介绍一下自己",
        "我要问你个问题",
        "这个问题可以换一个吗",
        "你还好吗",
        "I want to ask you something",
        "What is this project?",
        "This is a great project",
        "给我来讲讲",
        "想试试聊天",
        "想参加聊天",
    ],
)
def test_food_gate_default_substantive_speech_enters_talk_only_chat(transcript):
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()
        _enter_food_gate(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, transcript)
        detail = service.participant_detail(participant.id)

        assert result["stage"] == "talk_only_chat"
        assert result["chat_mode"] == CHAT_MODE_C_TALK_ONLY
        assert result["food_gate_result"] == "WANT_CHAT"
        assert result["next_action"] == "talk_only_chat"
        assert result["talk_only_chat_count"] == 0
        assert detail["draws"] == []
        assert detail["answers"] == []
        assert result["assignment"] is None
    finally:
        conn.close()


@pytest.mark.parametrize(
    "transcript",
    [
        "你为什么做吃的",
        "为什么是一个AI来做吃的",
        "你为什么来这里做吃的",
        "食物有什么意义",
        "这些食物代表什么",
        "为什么是艾苗",
        "Why are you serving food?",
        "What does the food mean?",
    ],
)
def test_food_gate_explanation_questions_enter_talk_only_and_reply_now(transcript):
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()
        _enter_food_gate(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, transcript)
        detail = service.participant_detail(participant.id)

        assert result["stage"] == "talk_only_chat"
        assert result["chat_mode"] == CHAT_MODE_C_TALK_ONLY
        assert result["food_gate_result"] == "WANT_CHAT"
        assert result["next_action"] == "talk_only_chat"
        assert result["talk_only_chat_count"] == 1
        assert result["interpretation"] == {"route": "chitchat", "count": 1}
        assert detail["draws"] == []
        assert detail["answers"] == []
        assert result["assignment"] is None
    finally:
        conn.close()


@pytest.mark.parametrize(
    "transcript",
    [
        "吃",
        "想吃",
        "要吃",
        "吃点",
        "吃一点",
        "想吃点什么",
        "我要吃东西",
        "来点吃的",
        "整点吃的",
        "整整点吃的",
        "搞点饭",
        "给我来点吃的",
        "干饭",
        "开饭",
        "我饿了",
        "好，吃",
        "吃饭",
        "参加",
        "想试试",
        "来吧",
        "yes",
        "ok",
        "eat",
        "food",
        "meal",
        "snack",
        "want food",
        "I want to eat",
        "I would like something to eat",
        "I'm hungry",
        "想试试吃的",
        "想参加吃的",
    ],
)
def test_food_gate_food_intents_start_formal_questions(transcript):
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()
        _enter_food_gate(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, transcript)

        assert result["stage"] == "formal_question_1"
        assert result["chat_mode"] == CHAT_MODE_B_WANT_FOOD
        assert result["food_gate_result"] == "WANT_FOOD"
        assert result["next_action"] == "answer_formal_question"
        assert len(service.participant_detail(participant.id)["draws"]) == 2
    finally:
        conn.close()


@pytest.mark.parametrize("transcript", ["吃点吧", "吃点儿吧", "那吃点吧", "来点吧"])
def test_food_gate_ambiguous_eating_intents_can_use_llm_to_start_formal_questions(
    transcript,
):
    conn, service, orchestrator, repo = _conversation_stack(
        [],
        food_gate_results=[
            FoodGateIntentInterpretation(
                route="want_food",
                confidence=0.91,
                rationale="The visitor wants a little food.",
                detected_language="zh",
                raw_json={"route": "want_food"},
            )
        ],
    )
    try:
        participant = service.create_participant()
        _enter_food_gate(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, transcript)

        assert result["stage"] == "formal_question_1"
        assert result["chat_mode"] == CHAT_MODE_B_WANT_FOOD
        assert result["food_gate_result"] == "WANT_FOOD"
        assert result["next_action"] == "answer_formal_question"
        assert len(service.participant_detail(participant.id)["draws"]) == 2
        assert repo.get_answers(participant.id) == []
        assert repo.get_voice_interpretations(participant.id) == []
        assert service._rubric_interpreter.calls == []
        assert orchestrator._food_gate_interpreter.calls[0]["transcript"] == transcript
    finally:
        conn.close()


@pytest.mark.parametrize("transcript", ["我要问你个问题", "这个项目是什么"])
def test_food_gate_default_chat_intents_can_use_llm_to_enter_talk_only_chat(
    transcript,
):
    conn, service, orchestrator, _repo = _conversation_stack(
        [],
        food_gate_results=[
            FoodGateIntentInterpretation(
                route="want_chat",
                confidence=0.9,
                rationale="The visitor is asking a side question.",
                detected_language="zh",
                raw_json={"route": "want_chat"},
            )
        ],
    )
    try:
        participant = service.create_participant()
        _enter_food_gate(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, transcript)
        detail = service.participant_detail(participant.id)

        assert result["stage"] == "talk_only_chat"
        assert result["chat_mode"] == CHAT_MODE_C_TALK_ONLY
        assert result["food_gate_result"] == "WANT_CHAT"
        assert detail["draws"] == []
        assert detail["answers"] == []
        assert service._rubric_interpreter.calls == []
        assert orchestrator._food_gate_interpreter.calls[0]["transcript"] == transcript
    finally:
        conn.close()


def test_food_gate_explicit_chat_intent_stays_local_and_skips_llm():
    conn, service, orchestrator, _repo = _conversation_stack([], food_gate_results=[])
    try:
        participant = service.create_participant()
        _enter_food_gate(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, "说说话吧")

        assert result["stage"] == "talk_only_chat"
        assert result["chat_mode"] == CHAT_MODE_C_TALK_ONLY
        assert result["food_gate_result"] == "WANT_CHAT"
        assert service.participant_detail(participant.id)["draws"] == []
        assert orchestrator._food_gate_interpreter.calls == []
    finally:
        conn.close()


@pytest.mark.parametrize(
    "transcript",
    [
        "不吃",
        "不想吃",
        "不要吃",
        "不用",
        "先不吃",
        "算了",
        "我不饿",
        "不用吃",
        "只是看看",
        "路过",
        "不参加",
        "no",
        "not now",
        "no food",
        "no thanks",
        "not hungry",
        "I am not hungry",
        "I do not need food",
    ],
)
def test_food_gate_no_food_intents_enter_not_eating_chat(transcript):
    conn, service, orchestrator, _repo = _conversation_stack([], food_gate_results=[])
    try:
        participant = service.create_participant()
        _enter_food_gate(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, transcript)

        assert result["stage"] == "not_eating_chat"
        assert result["chat_mode"] == CHAT_MODE_A_NO_FOOD
        assert result["food_gate_result"] == "NO_FOOD"
        assert result["next_action"] == "not_eating_chat"
        assert service.participant_detail(participant.id)["draws"] == []
        assert service._rubric_interpreter.calls == []
        assert orchestrator._food_gate_interpreter.calls == []
    finally:
        conn.close()


@pytest.mark.parametrize("food_gate_result", [None, RuntimeError("llm unavailable")])
def test_food_gate_llm_failure_uses_local_fallback(food_gate_result):
    conn, service, orchestrator, _repo = _conversation_stack(
        [],
        food_gate_results=[food_gate_result],
    )
    try:
        participant = service.create_participant()
        _enter_food_gate(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, "吃点吧")
        detail = service.participant_detail(participant.id)

        assert result["stage"] == "talk_only_chat"
        assert result["chat_mode"] == CHAT_MODE_C_TALK_ONLY
        assert result["food_gate_result"] == "WANT_CHAT"
        assert detail["draws"] == []
        assert detail["answers"] == []
        assert service._rubric_interpreter.calls == []
        assert len(orchestrator._food_gate_interpreter.calls) == 1
    finally:
        conn.close()


def test_talk_only_chat_deletes_transient_participant_on_third_chat_turn():
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()
        _enter_food_gate(orchestrator, participant.id)
        entered = orchestrator.handle_turn(participant.id, "不吃，聊聊吧")

        first = orchestrator.handle_turn(participant.id, "你是谁啊")
        second = orchestrator.handle_turn(participant.id, "这个地方有点奇怪")
        third = orchestrator.handle_turn(participant.id, "你想聊什么")

        assert entered["stage"] == "talk_only_chat"
        assert first["talk_only_chat_count"] == 1
        assert second["talk_only_chat_count"] == 2
        assert third["stage"] == "done"
        assert third["next_action"] == "end_session"
        assert third["participant_deleted"] is True
        with pytest.raises(KeyError):
            service.participant_detail(participant.id)
    finally:
        conn.close()


def test_not_eating_chat_deletes_transient_participant_on_third_chat_turn():
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()
        _enter_food_gate(orchestrator, participant.id)
        orchestrator.handle_turn(participant.id, "先不吃了")

        first = orchestrator.handle_turn(participant.id, "这个摊位好好玩")
        second = orchestrator.handle_turn(participant.id, "我今天有点累")
        third = orchestrator.handle_turn(participant.id, "你是谁啊")

        assert first["stage"] == "not_eating_chat"
        assert first["not_eating_chat_count"] == 1
        assert second["not_eating_chat_count"] == 2
        assert third["stage"] == "done"
        assert third["next_action"] == "end_session"
        assert third["participant_deleted"] is True
        with pytest.raises(KeyError):
            service.participant_detail(participant.id)
    finally:
        conn.close()


def test_want_food_starts_two_formal_questions():
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()
        _enter_food_gate(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, "想吃")
        detail = service.participant_detail(participant.id)

        assert result["stage"] == "formal_question_1"
        assert result["chat_mode"] == CHAT_MODE_B_WANT_FOOD
        assert result["food_gate_result"] == "WANT_FOOD"
        assert result["next_action"] == "answer_formal_question"
        assert result["answered_count"] == 0
        assert result["total_questions"] == 2
        assert len(detail["draws"]) == 2
        assert detail["draws"][0]["module_id"] == "soup_salad"
        assert detail["draws"][1]["module_id"] == "normal_aimiao"
        assert result["current_question_id"] == detail["draws"][0]["question_id"]
        assert "先回答我两个问题" in result["reply_text"]
    finally:
        conn.close()


def test_english_language_selection_keeps_formal_question_in_english():
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()
        orchestrator.handle_turn(participant.id, "")
        orchestrator.handle_turn(participant.id, "en")

        result = orchestrator.handle_turn(participant.id, "yes")
        detail = service.participant_detail(participant.id)

        assert result["stage"] == "formal_question_1"
        assert result["response_language"] == "en"
        assert result["answered_count"] == 0
        assert len(detail["draws"]) == 2
        assert result["current_question_text"] == detail["draws"][0]["question_text"]
        assert detail["draws"][0]["question_text_zh"] not in result["reply_text"]
        assert "First question" in result["reply_text"]
    finally:
        conn.close()


def test_one_formal_answer_never_assigns_and_points_to_second_question():
    conn, service, orchestrator, repo = _conversation_stack([
        RubricInterpretation("A", 0.9, "清楚。", "Clear.", "zh", {}),
    ])
    try:
        participant = service.create_participant()
        _enter_food_questions(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, "我选 A")
        detail = service.participant_detail(participant.id)

        assert result["stage"] == "formal_question_2"
        assert result["answered_count"] == 1
        assert result["next_action"] == "answer_formal_question"
        assert result["interpretation"] == {
            "status": "accepted",
            "choice": "A",
            "confidence": 0.9,
        }
        assert result["assignment"] is None
        assert result["current_question_id"] == detail["draws"][1]["question_id"]
        assert len(repo.get_answers(participant.id)) == 1
        assert service.get_assignment_if_exists(participant.id) is None
    finally:
        conn.close()


def test_two_accepted_answers_assign_aimiao_soup():
    conn, service, orchestrator, _repo = _conversation_stack([
        RubricInterpretation("A", 0.9, "清楚。", "Clear.", "zh", {}),
        RubricInterpretation("A", 0.9, "清楚。", "Clear.", "zh", {}),
    ])
    try:
        participant = service.create_participant()
        _enter_food_questions(orchestrator, participant.id)
        orchestrator.handle_turn(participant.id, "我选 A")

        result = orchestrator.handle_turn(participant.id, "我选 A")

        assert result["stage"] == "post_assignment_chat"
        assert "我给你定的是" in result["reply_text"]
        assert "你是A零零一号顾客" in result["reply_text"]
        assert "吃完最后想想我为什么给你这个" in result["reply_text"]
        assert "艾苗汤" in result["reply_text"]
        assert "Ai Miao soup" not in result["reply_text"]
        assert result["answered_count"] == 2
        assert result["next_action"] == "post_assignment_chat"
        assert result["post_assignment_chat_count"] == 0
        assert result["assignment"]["food_code"] == "aimiao_soup"
    finally:
        conn.close()


def test_assigned_turn_does_not_change_assignment():
    conn, service, orchestrator, _repo = _conversation_stack([
        RubricInterpretation("A", 0.9, "清楚。", "Clear.", "zh", {}),
        RubricInterpretation("B", 0.9, "清楚。", "Clear.", "zh", {}),
    ])
    try:
        participant = service.create_participant()
        _enter_food_questions(orchestrator, participant.id)
        orchestrator.handle_turn(participant.id, "我选 A")
        ready = orchestrator.handle_turn(participant.id, "我选 B")

        followup = orchestrator.handle_turn(participant.id, "我想换一个")

        assert followup["stage"] == "post_assignment_chat"
        assert followup["post_assignment_chat_count"] == 1
        assert followup["answered_count"] == 2
        assert followup["assignment"]["assignment_id"] == ready["assignment"]["assignment_id"]
        assert followup["assignment"]["food_code"] == ready["assignment"]["food_code"]
    finally:
        conn.close()


def test_scoring_engine_called_once_after_two_formal_answers():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    configs = load_have_some_ai_config(Path("config/have_some_ai"))
    bank = QuestionBank(configs["questions"], rng=random.Random(7))
    repo = MealRepository(conn)
    scoring = CountingScoringEngine(configs["scoring"], bank)
    service = MealService(
        repo,
        bank,
        scoring,
        rubric_interpreter=FakeRubricInterpreter([
            RubricInterpretation("A", 0.9, "清楚。", "Clear.", "zh", {}),
            RubricInterpretation("B", 0.9, "清楚。", "Clear.", "zh", {}),
        ]),
    )
    orchestrator = ConversationOrchestrator(service)
    try:
        participant = service.create_participant()
        _enter_food_questions(orchestrator, participant.id)
        orchestrator.handle_turn(participant.id, "我选 A")
        ready = orchestrator.handle_turn(participant.id, "我选 B")
        first = orchestrator.handle_turn(participant.id, "我想换一个")
        second = orchestrator.handle_turn(participant.id, "为什么是这个")
        done = orchestrator.handle_turn(participant.id, "还能再聊一句吗")

        assert ready["stage"] == "post_assignment_chat"
        assert first["stage"] == "post_assignment_chat"
        assert second["stage"] == "post_assignment_chat"
        assert done["stage"] == "done"
        assert done["next_action"] == "end_session"
        assert scoring.calls == 1
    finally:
        conn.close()


def test_unclear_formal_answer_does_not_advance_or_store_answer():
    conn, service, orchestrator, repo = _conversation_stack([
        RubricInterpretation("B", 0.4, "不清楚。", "Unclear.", "zh", {}),
    ])
    try:
        participant = service.create_participant()
        question = _enter_food_questions(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, "可能吧")

        assert result["stage"] == "formal_question_1"
        assert result["answered_count"] == 0
        assert result["current_question_id"] == question["current_question_id"]
        assert result["next_action"] == "repeat_current_question"
        assert result["interpretation"] == {"status": "unclear", "source": "judge"}
        assert result["assignment"] is None
        assert repo.get_answers(participant.id) == []
    finally:
        conn.close()


@pytest.mark.parametrize(
    "transcript",
    [
        "好",
        "好吧",
        "好的",
        "行",
        "行吧",
        "可以",
        "ok",
        "sure",
    ],
)
def test_acknowledgement_during_formal_question_can_be_chitchat_from_judge(
    transcript,
):
    conn, service, orchestrator, repo = _conversation_stack([
        RubricInterpretation(None, 0.9, "闲聊。", "Chitchat.", "zh", {}, route="chitchat"),
    ])
    try:
        participant = service.create_participant()
        question = _enter_food_questions(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, transcript)

        assert result["stage"] == "formal_question_1"
        assert result["current_question_id"] == question["current_question_id"]
        assert result["next_action"] == "repeat_current_question"
        assert result["interpretation"] == {"route": "chitchat", "count": 1}
        assert repo.get_answers(participant.id) == []
        assert repo.get_voice_interpretations(participant.id) == []
        assert service._rubric_interpreter.calls
    finally:
        conn.close()


@pytest.mark.parametrize("transcript", ["好", "行", "可以", "ok", "sure"])
def test_short_acknowledgement_can_be_accepted_by_formal_judge(transcript):
    conn, service, orchestrator, repo = _conversation_stack([
        RubricInterpretation("A", 0.9, "可映射到 A。", "Maps to A.", "zh", {}),
    ])
    try:
        participant = service.create_participant()
        _enter_food_questions(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, transcript)

        assert result["interpretation"]["status"] == "accepted"
        assert result["interpretation"]["choice"] == "A"
        assert len(repo.get_answers(participant.id)) == 1
        assert len(repo.get_voice_interpretations(participant.id)) == 1
        assert service._rubric_interpreter.calls
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("transcript", "expected_next_action", "expected_route"),
    [
        ("", "answer_formal_question", None),
        ("嗯", "repeat_current_question", "unclear_speech"),
        ("啊", "repeat_current_question", "unclear_speech"),
        ("呃", "repeat_current_question", "unclear_speech"),
        ("um", "repeat_current_question", "unclear_speech"),
        ("uh", "repeat_current_question", "unclear_speech"),
    ],
)
def test_noise_and_fillers_during_formal_question_skip_rubric(
    transcript,
    expected_next_action,
    expected_route,
):
    conn, service, orchestrator, repo = _conversation_stack([
        RubricInterpretation("A", 0.9, "清楚。", "Clear.", "zh", {}),
    ])
    try:
        participant = service.create_participant()
        question = _enter_food_questions(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, transcript)

        assert result["stage"] == "formal_question_1"
        assert result["current_question_id"] == question["current_question_id"]
        assert result["next_action"] == expected_next_action
        if expected_route is None:
            assert result["interpretation"] is None
        else:
            assert result["interpretation"] == {"route": expected_route}
        assert repo.get_answers(participant.id) == []
        assert service._rubric_interpreter.calls == []
    finally:
        conn.close()


def test_formal_chitchat_from_judge_is_not_stored_and_is_limited():
    conn, service, orchestrator, repo = _conversation_stack([
        RubricInterpretation(None, 0.9, "闲聊。", "Chitchat.", "zh", {}, route="chitchat"),
        RubricInterpretation(None, 0.9, "闲聊。", "Chitchat.", "zh", {}, route="chitchat"),
        RubricInterpretation(None, 0.9, "闲聊。", "Chitchat.", "zh", {}, route="chitchat"),
    ])
    try:
        participant = service.create_participant()
        question = _enter_food_questions(orchestrator, participant.id)

        first = orchestrator.handle_turn(participant.id, "你觉得这个项目好吗？")
        second = orchestrator.handle_turn(participant.id, "哈哈那你吃不吃？")
        third = orchestrator.handle_turn(participant.id, "为什么非要问这个？")

        assert first["stage"] == "formal_question_1"
        assert first["formal_chitchat_count"] == 1
        assert second["formal_chitchat_count"] == 2
        assert third["formal_chitchat_count"] == 3
        assert "回到这题" in third["reply_text"]
        assert third["current_question_id"] == question["current_question_id"]
        assert repo.get_answers(participant.id) == []
        assert repo.get_voice_interpretations(participant.id) == []
        assert len(service._rubric_interpreter.calls) == 3
    finally:
        conn.close()


def test_unrelated_formal_speech_can_be_classified_as_chitchat_by_judge():
    conn, service, orchestrator, repo = _conversation_stack([
        RubricInterpretation(None, 0.9, "闲聊。", "Chitchat.", "zh", {}, route="chitchat"),
        RubricInterpretation(None, 0.9, "闲聊。", "Chitchat.", "zh", {}, route="chitchat"),
        RubricInterpretation(None, 0.9, "闲聊。", "Chitchat.", "zh", {}, route="chitchat"),
    ])
    try:
        participant = service.create_participant()
        question = _enter_food_questions(orchestrator, participant.id)

        first = orchestrator.handle_turn(
            participant.id,
            "我今天刚从学校过来，外面还在下雨",
        )
        second = orchestrator.handle_turn(participant.id, "旁边那个机器声音有点怪")
        third = orchestrator.handle_turn(participant.id, "我朋友刚才还在笑这个项目")

        assert first["stage"] == "formal_question_1"
        assert first["interpretation"] == {"route": "chitchat", "count": 1}
        assert first["formal_chitchat_count"] == 1
        assert second["formal_chitchat_count"] == 2
        assert third["formal_chitchat_count"] == 3
        assert "回到这题" in third["reply_text"]
        assert third["current_question_id"] == question["current_question_id"]
        assert repo.get_answers(participant.id) == []
        assert repo.get_voice_interpretations(participant.id) == []
        assert len(service._rubric_interpreter.calls) == 3
    finally:
        conn.close()


def test_formal_chitchat_with_generic_yes_no_words_is_not_answer_attempt():
    conn, service, orchestrator, repo = _conversation_stack(
        [
            RubricInterpretation("A", 0.93, "清楚选择 A。", "Clear A.", "zh", {}),
            RubricInterpretation(None, 0.9, "闲聊。", "Chitchat.", "zh", {}, route="chitchat"),
            RubricInterpretation(None, 0.9, "闲聊。", "Chitchat.", "zh", {}, route="chitchat"),
        ],
        rng_seed=7,
    )
    try:
        participant = service.create_participant()
        _enter_food_questions(orchestrator, participant.id)

        accepted = orchestrator.handle_turn(participant.id, "我选 A")
        first = orchestrator.handle_turn(participant.id, "旁边那个机器声音有点怪")
        second = orchestrator.handle_turn(participant.id, "我现在有点紧张")

        assert accepted["stage"] == "formal_question_2"
        assert first["stage"] == "formal_question_2"
        assert first["interpretation"] == {"route": "chitchat", "count": 1}
        assert first["formal_chitchat_count"] == 1
        assert second["formal_chitchat_count"] == 2
        assert len(repo.get_answers(participant.id)) == 1
        assert len(repo.get_voice_interpretations(participant.id)) == 1
        assert len(service._rubric_interpreter.calls) == 3
    finally:
        conn.close()


@pytest.mark.parametrize(
    "transcript",
    [
        "我觉得你挺有意思",
        "我喜欢这个地方",
        "你这个店到底是干嘛的？",
        "这个问题让我有点烦",
        "我现在不太想回答",
        "刚才那个人很好笑",
    ],
)
def test_substantive_non_answer_formal_speech_defaults_to_chitchat(transcript):
    conn, service, orchestrator, repo = _conversation_stack([
        RubricInterpretation(None, 0.9, "闲聊。", "Chitchat.", "zh", {}, route="chitchat"),
    ])
    try:
        participant = service.create_participant()
        question = _enter_food_questions(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, transcript)

        assert result["stage"] == "formal_question_1"
        assert result["current_question_id"] == question["current_question_id"]
        assert result["next_action"] == "repeat_current_question"
        assert result["interpretation"] == {"route": "chitchat", "count": 1}
        assert repo.get_answers(participant.id) == []
        assert repo.get_voice_interpretations(participant.id) == []
        assert service._rubric_interpreter.calls
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("transcript", "rng_seed", "rubric"),
    [
        ("我选 B", 7, RubricInterpretation("B", 0.93, "清楚选择 B。", "Clear B.", "zh", {})),
        ("我通常不关门", 2, RubricInterpretation("B", 0.9, "清楚。", "Clear.", "zh", {})),
        ("我觉得有", 7, RubricInterpretation("A", 0.9, "清楚。", "Clear.", "zh", {})),
        ("应该没有吧", 7, RubricInterpretation("B", 0.9, "清楚。", "Clear.", "zh", {})),
        ("算是吧", 7, RubricInterpretation("A", 0.9, "清楚。", "Clear.", "zh", {})),
        ("yes", 7, RubricInterpretation("A", 0.9, "清楚。", "Clear.", "en", {})),
        ("probably yes", 7, RubricInterpretation("A", 0.9, "清楚。", "Clear.", "en", {})),
        ("no", 7, RubricInterpretation("B", 0.9, "清楚。", "Clear.", "en", {})),
        ("probably not", 7, RubricInterpretation("B", 0.9, "清楚。", "Clear.", "en", {})),
        ("我选 A 吧", 7, RubricInterpretation("A", 0.9, "清楚。", "Clear.", "zh", {})),
        ("我倾向 B", 7, RubricInterpretation("B", 0.9, "清楚。", "Clear.", "zh", {})),
        ("有", 7, RubricInterpretation("A", 0.4, "不清楚。", "Unclear.", "zh", {})),
        ("是", 7, RubricInterpretation("A", 0.4, "不清楚。", "Unclear.", "zh", {})),
        ("都行", 7, RubricInterpretation("B", 0.4, "不清楚。", "Unclear.", "zh", {})),
        ("不知道", 7, RubricInterpretation("A", 0.4, "不清楚。", "Unclear.", "zh", {})),
        ("可能吧", 7, RubricInterpretation("A", 0.4, "不清楚。", "Unclear.", "zh", {})),
    ],
)
def test_formal_answer_like_speech_still_uses_rubric(transcript, rng_seed, rubric):
    conn, service, orchestrator, _repo = _conversation_stack([rubric], rng_seed=rng_seed)
    try:
        participant = service.create_participant()
        _enter_food_questions(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, transcript)

        assert result["interpretation"] != {"route": "chitchat", "count": 1}
        assert service._rubric_interpreter.calls
    finally:
        conn.close()


def test_question_related_formal_speech_still_uses_rubric_on_second_question():
    conn, service, orchestrator, repo = _conversation_stack([
        RubricInterpretation("A", 0.93, "清楚选择 A。", "Clear A.", "zh", {}),
        RubricInterpretation("B", 0.93, "清楚选择 B。", "Clear B.", "zh", {}),
    ])
    try:
        participant = service.create_participant()
        _enter_food_questions(orchestrator, participant.id)

        first = orchestrator.handle_turn(participant.id, "我选 A")
        second = orchestrator.handle_turn(participant.id, "我没有向 ai 道过歉")

        assert first["stage"] == "formal_question_2"
        assert second["interpretation"] != {"route": "chitchat", "count": 1}
        assert len(repo.get_answers(participant.id)) == 2
        assert len(service._rubric_interpreter.calls) == 2
    finally:
        conn.close()


def test_orchestrator_decides_flow_reply_service_only_supplies_text():
    conn, service, _orchestrator, _repo = _conversation_stack([])
    orchestrator = ConversationOrchestrator(service, reply_service=FixedReplyService())
    try:
        participant = service.create_participant()

        result = orchestrator.handle_turn(participant.id, "")

        assert result["reply_text"] == "店主说话归店主，流程归流程。"
        assert result["stage"] == "language_gate"
        assert result["next_action"] == "choose_language"
        assert result["answered_count"] == 0
        assert result["assignment"] is None
    finally:
        conn.close()


def test_conversation_turn_api_returns_language_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        response = client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
                json={"transcript": ""},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["stage"] == "language_gate"
    assert payload["next_action"] == "choose_language"
    assert payload["total_questions"] == 2
    assert payload["assignment"] is None


def _conversation_stack(results, *, rng_seed=7, food_gate_results=None):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)

    configs = load_have_some_ai_config(Path("config/have_some_ai"))
    bank = QuestionBank(configs["questions"], rng=random.Random(rng_seed))
    repo = MealRepository(conn)
    service = MealService(
        repo,
        bank,
        ScoringEngine(configs["scoring"], bank),
        rubric_interpreter=FakeRubricInterpreter(results),
    )
    food_gate_interpreter = (
        FakeFoodGateIntentInterpreter(food_gate_results)
        if food_gate_results is not None
        else None
    )
    return (
        conn,
        service,
        ConversationOrchestrator(
            service,
            food_gate_interpreter=food_gate_interpreter,
        ),
        repo,
    )


def _enter_food_questions(
    orchestrator: ConversationOrchestrator,
    participant_id: str,
) -> dict:
    _enter_food_gate(orchestrator, participant_id)
    return orchestrator.handle_turn(participant_id, "想吃")


def _enter_food_gate(
    orchestrator: ConversationOrchestrator,
    participant_id: str,
) -> dict:
    orchestrator.handle_turn(participant_id, "")
    return orchestrator.handle_turn(participant_id, "中文")
