from __future__ import annotations

from pathlib import Path

from have_some_ai.config import load_have_some_ai_config
from have_some_ai.models import Answer, ObservationEvent
from have_some_ai.questionnaire import QuestionBank
from have_some_ai.scoring import ScoringEngine


def test_scoring_maps_dual_axes_to_ai_sprout_soup():
    configs = load_have_some_ai_config(Path("config/have_some_ai"))
    bank = QuestionBank(configs["questions"])
    engine = ScoringEngine(configs["scoring"], bank)

    assignment = engine.assign(
        "participant-1",
        [
            Answer("participant-1", "m1_thank_ai", "A"),
            Answer("participant-1", "m2_door", "A"),
            Answer("participant-1", "m3_project_good", "B"),
        ],
        [ObservationEvent("participant-1", "leaned_in", confidence=1.0)],
    )

    assert assignment.food_code == "ai_sprout_soup"
    assert assignment.ai_trace_score >= 2.0
    assert assignment.relational_score >= 0.0


def test_scoring_maps_low_ai_bounded_subject_to_salad():
    configs = load_have_some_ai_config(Path("config/have_some_ai"))
    bank = QuestionBank(configs["questions"])
    engine = ScoringEngine(configs["scoring"], bank)

    assignment = engine.assign(
        "participant-1",
        [
            Answer("participant-1", "m1_thank_ai", "B"),
            Answer("participant-1", "m2_door", "B"),
            Answer("participant-1", "m3_project_good", "A"),
        ],
        [],
    )

    assert assignment.food_code == "salad"
    assert assignment.ai_trace_score < 2.0
    assert assignment.relational_score < 0.0
