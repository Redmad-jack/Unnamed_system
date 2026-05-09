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
    ConversationOrchestrator,
)
from have_some_ai.db import run_migrations
from have_some_ai.interfaces.api import app
from have_some_ai.questionnaire import QuestionBank
from have_some_ai.repository import MealRepository
from have_some_ai.scoring import ScoringEngine
from have_some_ai.service import MealService
from have_some_ai.voice import RubricInterpretation


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
        assert "Would you like to continue in English or 中文" in result["reply_text"]
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
            "make my staff wear them on shift. Want something to eat?"
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


def test_food_gate_chitchat_is_not_unclear_and_does_not_default_to_no_food():
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()
        _enter_food_gate(orchestrator, participant.id)

        unclear = orchestrator.handle_turn(participant.id, "嗯")
        chitchat = orchestrator.handle_turn(participant.id, "你是谁啊")

        assert unclear["stage"] == "food_gate"
        assert unclear["interpretation"] == {"route": "unclear_speech"}
        assert chitchat["stage"] == "food_gate"
        assert chitchat["interpretation"] == {"route": "chitchat", "count": 1}
        assert chitchat["next_action"] == "answer_food_gate"
        assert chitchat["chat_mode"] is None
        assert service.participant_detail(participant.id)["draws"] == []
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

        assert result["stage"] == "farewell"
        assert "我给你定的是" in result["reply_text"]
        assert "吃完猜猜我为什么给你这个东西" in result["reply_text"]
        assert "艾苗汤 / Ai Miao soup" in result["reply_text"]
        assert result["answered_count"] == 2
        assert result["next_action"] == "end_session"
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

        assigned = orchestrator.handle_turn(participant.id, "我想换一个")

        assert assigned["stage"] == "assigned"
        assert "换下一个人吧" in assigned["reply_text"]
        assert "汤 / Soup" in assigned["reply_text"]
        assert assigned["answered_count"] == 2
        assert assigned["assignment"]["assignment_id"] == ready["assignment"]["assignment_id"]
        assert assigned["assignment"]["food_code"] == ready["assignment"]["food_code"]
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
        farewell = orchestrator.handle_turn(participant.id, "我选 B")
        assigned = orchestrator.handle_turn(participant.id, "我想换一个")

        assert farewell["stage"] == "farewell"
        assert assigned["stage"] == "assigned"
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


def test_acknowledgement_during_formal_question_is_chitchat_without_rubric_call():
    conn, service, orchestrator, repo = _conversation_stack([
        RubricInterpretation("A", 0.9, "清楚。", "Clear.", "zh", {}),
    ])
    try:
        participant = service.create_participant()
        question = _enter_food_questions(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, "好吧")

        assert result["stage"] == "formal_question_1"
        assert result["current_question_id"] == question["current_question_id"]
        assert result["next_action"] == "repeat_current_question"
        assert result["interpretation"] == {"route": "chitchat", "count": 1}
        assert repo.get_answers(participant.id) == []
        assert service._rubric_interpreter.calls == []
    finally:
        conn.close()


def test_formal_chitchat_is_routed_before_judge_and_limited():
    conn, service, orchestrator, repo = _conversation_stack([])
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
        assert service._rubric_interpreter.calls == []
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


def _conversation_stack(results):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)

    configs = load_have_some_ai_config(Path("config/have_some_ai"))
    bank = QuestionBank(configs["questions"], rng=random.Random(7))
    repo = MealRepository(conn)
    service = MealService(
        repo,
        bank,
        ScoringEngine(configs["scoring"], bank),
        rubric_interpreter=FakeRubricInterpreter(results),
    )
    return conn, service, ConversationOrchestrator(service), repo


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
