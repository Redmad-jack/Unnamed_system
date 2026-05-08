from __future__ import annotations

from pathlib import Path

import pytest

from have_some_ai.config import load_have_some_ai_config
from have_some_ai.models import Answer, ObservationEvent
from have_some_ai.questionnaire import QuestionBank
from have_some_ai.scoring import ScoringEngine


def test_scoring_maps_soup_and_aimiao_to_aimiao_soup():
    engine = _engine()

    assignment = engine.assign(
        "participant-1",
        [
            Answer("participant-1", "m2_door", "A"),
            Answer("participant-1", "m1_thank_ai", "A"),
        ],
        [ObservationEvent("participant-1", "leaned_in", confidence=1.0)],
    )

    assert assignment.food_code == "aimiao_soup"
    assert assignment.ai_trace_score == 1.0
    assert assignment.relational_score == 1.0
    assert assignment.rationale["mapping"] == {
        "soup_salad": "soup",
        "normal_aimiao": "aimiao",
    }
    assert assignment.rationale["observations"][0]["used_for_assignment"] is False


def test_scoring_maps_salad_and_normal_to_salad():
    engine = _engine()

    assignment = engine.assign(
        "participant-1",
        [
            Answer("participant-1", "m2_door", "B"),
            Answer("participant-1", "m1_thank_ai", "B"),
        ],
        [],
    )

    assert assignment.food_code == "salad"
    assert assignment.ai_trace_score == 0.0
    assert assignment.relational_score == -1.0


def test_scoring_requires_both_formal_axes():
    engine = _engine()

    with pytest.raises(ValueError, match="normal/aimiao"):
        engine.assign(
            "participant-1",
            [Answer("participant-1", "m2_door", "A")],
            [],
        )


def _engine() -> ScoringEngine:
    configs = load_have_some_ai_config(Path("config/have_some_ai"))
    bank = QuestionBank(configs["questions"])
    return ScoringEngine(configs["scoring"], bank)
