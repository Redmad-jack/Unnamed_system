from __future__ import annotations

import random
import sqlite3
from pathlib import Path

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


def test_new_participant_first_turn_asks_food_gate_without_draws():
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()

        result = orchestrator.handle_turn(participant.id, "你好")
        detail = service.participant_detail(participant.id)

        assert result["stage"] == "food_gate"
        assert result["next_action"] == "answer_food_gate"
        assert result["total_questions"] == 2
        assert result["current_question_id"] is None
        assert result["assignment"] is None
        assert "想来点吃的吗？" in result["reply_text"]
        assert len(detail["draws"]) == 0
        assert len(detail["answers"]) == 0
    finally:
        conn.close()


def test_no_food_enters_free_chat_and_never_draws_questions():
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()
        orchestrator.handle_turn(participant.id, "")

        result = orchestrator.handle_turn(participant.id, "先不吃了")
        detail = service.participant_detail(participant.id)

        assert result["stage"] == "free_chat"
        assert result["chat_mode"] == CHAT_MODE_A_NO_FOOD
        assert result["food_gate_result"] == "NO_FOOD"
        assert result["next_action"] == "free_chat"
        assert result["assignment"] is None
        assert detail["draws"] == []
        assert detail["answers"] == []
    finally:
        conn.close()


def test_food_gate_unclear_once_clarifies_then_defaults_to_no_food():
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()
        orchestrator.handle_turn(participant.id, "")

        clarify = orchestrator.handle_turn(participant.id, "嗯")
        fallback = orchestrator.handle_turn(participant.id, "随便")

        assert clarify["stage"] == "food_gate_clarify"
        assert clarify["food_gate_result"] == "UNCLEAR"
        assert "想来点吃的，还是先不吃" in clarify["reply_text"]
        assert fallback["stage"] == "free_chat"
        assert fallback["chat_mode"] == CHAT_MODE_A_NO_FOOD
        assert fallback["food_gate_result"] == "UNCLEAR"
        assert service.participant_detail(participant.id)["draws"] == []
    finally:
        conn.close()


def test_want_food_starts_two_formal_questions():
    conn, service, orchestrator, _repo = _conversation_stack([])
    try:
        participant = service.create_participant()
        orchestrator.handle_turn(participant.id, "")

        result = orchestrator.handle_turn(participant.id, "想吃")
        detail = service.participant_detail(participant.id)

        assert result["stage"] == "asking_required_question"
        assert result["chat_mode"] == CHAT_MODE_B_WANT_FOOD
        assert result["food_gate_result"] == "WANT_FOOD"
        assert result["next_action"] == "submit_required_answer"
        assert result["answered_count"] == 0
        assert result["total_questions"] == 2
        assert len(detail["draws"]) == 2
        assert detail["draws"][0]["module_id"] == "soup_salad"
        assert detail["draws"][1]["module_id"] == "normal_aimiao"
        assert result["current_question_id"] == detail["draws"][0]["question_id"]
        assert "先回答我两个问题" in result["reply_text"]
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

        assert result["stage"] == "after_required_answer"
        assert result["answered_count"] == 1
        assert result["next_action"] == "ask_next_required_question"
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
        orchestrator.handle_turn(participant.id, "")

        result = orchestrator.handle_turn(participant.id, "我选 A")

        assert result["stage"] == "ready_to_assign"
        assert "系统给你定的是" in result["reply_text"]
        assert "艾苗汤 / Ai Miao soup" in result["reply_text"]
        assert result["answered_count"] == 2
        assert result["next_action"] == "assign"
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
        orchestrator.handle_turn(participant.id, "")
        ready = orchestrator.handle_turn(participant.id, "我选 B")

        assigned = orchestrator.handle_turn(participant.id, "我想换一个")

        assert assigned["stage"] == "assigned"
        assert "结果不会再改" in assigned["reply_text"]
        assert "汤 / Soup" in assigned["reply_text"]
        assert assigned["answered_count"] == 2
        assert assigned["assignment"]["assignment_id"] == ready["assignment"]["assignment_id"]
        assert assigned["assignment"]["food_code"] == ready["assignment"]["food_code"]
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

        assert result["stage"] == "awaiting_required_answer"
        assert result["answered_count"] == 0
        assert result["current_question_id"] == question["current_question_id"]
        assert result["next_action"] == "repeat_current_question"
        assert result["interpretation"] == {"status": "unclear"}
        assert result["assignment"] is None
        assert repo.get_answers(participant.id) == []
    finally:
        conn.close()


def test_acknowledgement_during_formal_question_repeats_without_rubric_call():
    conn, service, orchestrator, repo = _conversation_stack([
        RubricInterpretation("A", 0.9, "清楚。", "Clear.", "zh", {}),
    ])
    try:
        participant = service.create_participant()
        question = _enter_food_questions(orchestrator, participant.id)

        result = orchestrator.handle_turn(participant.id, "好吧")

        assert result["stage"] == "awaiting_required_answer"
        assert result["current_question_id"] == question["current_question_id"]
        assert result["next_action"] == "repeat_current_question"
        assert result["interpretation"] == {"status": "continue_ack"}
        assert repo.get_answers(participant.id) == []
        assert service._rubric_interpreter.calls == []
    finally:
        conn.close()


def test_food_chat_detours_are_limited_and_never_store_formal_answers():
    conn, service, orchestrator, repo = _conversation_stack([
        RubricInterpretation(None, 0.2, "打岔。", "Detour.", "zh", {}),
        RubricInterpretation(None, 0.2, "打岔。", "Detour.", "zh", {}),
        RubricInterpretation(None, 0.2, "打岔。", "Detour.", "zh", {}),
    ])
    try:
        participant = service.create_participant()
        question = _enter_food_questions(orchestrator, participant.id)

        first = orchestrator.handle_turn(participant.id, "你觉得这个项目好吗？")
        second = orchestrator.handle_turn(participant.id, "哈哈那你吃不吃？")
        third = orchestrator.handle_turn(participant.id, "为什么非要问这个？")

        assert first["stage"] == "food_chat_detour"
        assert first["food_chat_detour_count"] == 1
        assert second["stage"] == "food_chat_detour"
        assert second["food_chat_detour_count"] == 2
        assert third["stage"] == "food_chat_limit"
        assert third["food_chat_detour_count"] == 3
        assert "不聊那么多了" in third["reply_text"]
        assert third["current_question_id"] == question["current_question_id"]
        assert repo.get_answers(participant.id) == []
    finally:
        conn.close()


def test_orchestrator_decides_flow_reply_service_only_supplies_text():
    conn, service, _orchestrator, _repo = _conversation_stack([])
    orchestrator = ConversationOrchestrator(service, reply_service=FixedReplyService())
    try:
        participant = service.create_participant()

        result = orchestrator.handle_turn(participant.id, "你好")

        assert result["reply_text"] == "店主说话归店主，流程归流程。"
        assert result["stage"] == "food_gate"
        assert result["next_action"] == "answer_food_gate"
        assert result["answered_count"] == 0
        assert result["assignment"] is None
    finally:
        conn.close()


def test_conversation_turn_api_returns_food_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        response = client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": "你好"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["stage"] == "food_gate"
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
    orchestrator.handle_turn(participant_id, "")
    return orchestrator.handle_turn(participant_id, "想吃")
