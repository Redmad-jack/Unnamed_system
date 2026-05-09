from __future__ import annotations

import random
import sqlite3
from pathlib import Path

from have_some_ai.config import load_have_some_ai_config
from have_some_ai.db import run_migrations
from have_some_ai.questionnaire import QuestionBank
from have_some_ai.repository import MealRepository
from have_some_ai.scoring import ScoringEngine
from have_some_ai.service import MealService
from have_some_ai.voice import RubricInterpretation


class FakeRubricInterpreter:
    def __init__(self, results):
        self._results = list(results)

    def interpret(self, **_kwargs):
        return self._results.pop(0)


def test_service_runs_participant_assignment_flow():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)

    configs = load_have_some_ai_config(Path("config/have_some_ai"))
    bank = QuestionBank(configs["questions"], rng=random.Random(7))
    service = MealService(
        MealRepository(conn),
        bank,
        ScoringEngine(configs["scoring"], bank),
    )

    participant = service.create_participant(safety_flags={"raw": "no dairy"})
    draws = service.start_questionnaire(participant.id)

    assert participant.public_code == "A001"
    assert len(draws) == 2

    service.submit_answers(
        participant.id,
        [
            {"question_id": draw["question_id"], "option_id": "A"}
            for draw in draws
        ],
    )
    assignment = service.assign_food(participant.id)
    queue = service.list_staff_queue()

    assert assignment.food_code in {
        "soup",
        "salad",
        "aimiao_soup",
        "aimiao_salad",
    }
    assert len(queue) == 1
    assert queue[0]["public_code"] == "A001"

    conn.close()


def test_question_bank_loads_bilingual_text():
    configs = load_have_some_ai_config(Path("config/have_some_ai"))
    bank = QuestionBank(configs["questions"], rng=random.Random(7))

    question = bank.get_question("m1_thank_ai")

    assert question.text_zh
    assert question.options[0].text_zh


def test_question_speech_text_reads_only_question_with_flow_cues():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)

    configs = load_have_some_ai_config(Path("config/have_some_ai"))
    bank = QuestionBank(configs["questions"], rng=random.Random(7))
    service = MealService(
        MealRepository(conn),
        bank,
        ScoringEngine(configs["scoring"], bank),
    )

    participant = service.create_participant()
    draws = service.start_questionnaire(participant.id)
    first_text = service.question_speech_text(participant.id, draws[0]["question_id"])
    second_text = service.question_speech_text(participant.id, draws[1]["question_id"])

    assert "先回答我两个问题" in first_text
    assert "第一个问题" in first_text
    assert draws[0]["question_text_zh"] in first_text
    assert draws[0]["question_text"] in first_text
    assert "A." not in first_text
    assert "B." not in first_text
    assert "C." not in first_text
    assert "You can answer A, B, or C" not in first_text

    assert "第二个问题" in second_text
    assert "先回答我两个问题" not in second_text
    assert draws[1]["question_text_zh"] in second_text
    assert draws[1]["question_text"] in second_text
    assert "A." not in second_text
    assert "B." not in second_text
    assert "C." not in second_text

    conn.close()


def test_food_gate_prompt_rotates_by_public_code():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)

    configs = load_have_some_ai_config(Path("config/have_some_ai"))
    bank = QuestionBank(configs["questions"], rng=random.Random(7))
    service = MealService(
        MealRepository(conn),
        bank,
        ScoringEngine(configs["scoring"], bank),
    )

    participants = [service.create_participant() for _ in range(14)]

    assert service.food_gate_prompt(participants[0].id).startswith("你今天衣服很漂亮啊，我晚上")
    assert service.food_gate_prompt(participants[1].id).startswith("你好啊，先提前告诉你")
    assert service.food_gate_prompt(participants[12].id).startswith("你好，人类，一会")
    assert service.food_gate_prompt(participants[13].id).startswith("你今天衣服很漂亮啊，我晚上")
    assert service.food_gate_prompt(participants[0].id).endswith("想来点吃的吗？")
    assert service.food_gate_prompt(
        participants[0].id,
        response_language="en",
    ) == (
        "Your outfit looks pretty good today. I might buy some tonight and "
        "make my staff wear them on shift. Want something to eat?"
    )
    assert service.food_gate_prompt(
        participants[12].id,
        response_language="en",
    ).startswith("Hi, human.")
    assert service.food_gate_prompt(
        participants[13].id,
        response_language="en",
    ).startswith("Your outfit looks pretty good today.")

    conn.close()


def test_voice_answer_accepts_chinese_transcript_and_stores_answer():
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
        rubric_interpreter=FakeRubricInterpreter([
            RubricInterpretation(
                option_id="A",
                confidence=0.91,
                reason_zh="回答明确表示肯定。",
                reason_en="The answer clearly affirms the option.",
                detected_language="zh",
                raw_json={"option_id": "A", "confidence": 0.91},
            )
        ]),
    )

    participant = service.create_participant()
    draws = service.start_questionnaire(participant.id)
    result = service.submit_voice_answer(
        participant.id,
        question_id=draws[0]["question_id"],
        transcript="有，我真的对 AI 说过谢谢。",
        detected_language="zh",
        stt_confidence=0.9,
    )

    answers = repo.get_answers(participant.id)
    detail = service.participant_detail(participant.id)

    assert result["status"] == "accepted"
    assert result["option_id"] == "A"
    assert len(answers) == 1
    assert answers[0].option_id == "A"
    assert detail["voice_interpretations"][0]["transcript"] == "有，我真的对 AI 说过谢谢。"

    conn.close()


def test_voice_answer_accepts_confidence_at_055_threshold():
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
        rubric_interpreter=FakeRubricInterpreter([
            RubricInterpretation(
                option_id="A",
                confidence=0.56,
                reason_zh="回答明确表示 A。",
                reason_en="The answer clearly maps to A.",
                detected_language="zh",
                raw_json={"option_id": "A", "confidence": 0.56},
            )
        ]),
    )

    participant = service.create_participant()
    draws = service.start_questionnaire(participant.id)
    result = service.submit_voice_answer(
        participant.id,
        question_id=draws[0]["question_id"],
        transcript="我选 A。",
        detected_language="zh",
    )

    answers = repo.get_answers(participant.id)

    assert result["status"] == "accepted"
    assert result["option_id"] == "A"
    assert len(answers) == 1
    assert answers[0].option_id == "A"

    conn.close()


def test_voice_answer_low_confidence_is_unclear_without_answer():
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
        rubric_interpreter=FakeRubricInterpreter([
            RubricInterpretation(
                option_id="B",
                confidence=0.4,
                reason_zh="回答不够清楚。",
                reason_en="The answer is unclear.",
                detected_language="mixed",
                raw_json={"option_id": "B", "confidence": 0.4},
            )
        ]),
    )

    participant = service.create_participant()
    draws = service.start_questionnaire(participant.id)
    result = service.submit_voice_answer(
        participant.id,
        question_id=draws[0]["question_id"],
        transcript="Maybe, 不太确定。",
        detected_language="mixed",
    )

    assert result["status"] == "unclear"
    assert result["needs_retry"] is True
    assert repo.get_answers(participant.id) == []
    assert repo.get_voice_interpretations(participant.id)[0].status == "unclear"

    conn.close()


def test_voice_answer_empty_transcript_is_unclear_without_answer():
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
        rubric_interpreter=FakeRubricInterpreter([]),
    )

    participant = service.create_participant()
    draws = service.start_questionnaire(participant.id)
    result = service.submit_voice_answer(
        participant.id,
        question_id=draws[0]["question_id"],
        transcript="",
        detected_language="unknown",
        attempt_id="empty-service-attempt",
    )

    assert result["status"] == "unclear"
    assert result["needs_retry"] is True
    assert repo.get_answers(participant.id) == []
    assert repo.get_voice_interpretations(participant.id)[0].attempt_id == "empty-service-attempt"

    conn.close()


def test_two_accepted_voice_answers_can_assign_food():
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
        rubric_interpreter=FakeRubricInterpreter([
            RubricInterpretation("A", 0.9, "肯定。", "Affirmative.", "zh", {}),
            RubricInterpretation("A", 0.9, "肯定。", "Affirmative.", "en", {}),
        ]),
    )

    participant = service.create_participant()
    draws = service.start_questionnaire(participant.id)
    for draw in draws:
        service.submit_voice_answer(
            participant.id,
            question_id=draw["question_id"],
            transcript="yes 好的",
            detected_language="mixed",
        )

    assignment = service.assign_food(participant.id)
    queue = service.list_staff_queue()

    assert assignment.food_code in {
        "soup",
        "salad",
        "aimiao_soup",
        "aimiao_salad",
    }
    assert queue[0]["public_code"] == "A001"

    conn.close()
