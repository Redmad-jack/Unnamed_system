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
    assert len(draws) == 3

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
        "ai_sprout_soup",
        "ai_sprout_salad",
    }
    assert len(queue) == 1
    assert queue[0]["public_code"] == "A001"

    conn.close()
