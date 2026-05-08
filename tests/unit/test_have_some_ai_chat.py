from __future__ import annotations

from have_some_ai.chat import ShopkeeperReplyService


def test_shopkeeper_reply_service_returns_only_reply_text():
    service = ShopkeeperReplyService()

    result = service.generate_reply({
        "stage": "asking_required_question",
        "participant_status": "questioning",
        "answered_count": 0,
        "total_questions": 2,
        "current_question_text": "Have you ever sincerely said thank you to AI?",
        "last_user_transcript": "你好",
        "interpretation_status": None,
        "assignment": None,
    })

    assert set(result) == {"reply_text"}
    assert result["reply_text"]


def test_shopkeeper_prompt_excludes_internal_scoring_and_food_code_logic():
    service = ShopkeeperReplyService()

    prompt = service.build_prompt({
        "stage": "assigned",
        "participant_status": "assigned",
        "answered_count": 2,
        "total_questions": 2,
        "current_question_text": None,
        "last_user_transcript": "为什么是这个？",
        "interpretation_status": None,
        "assignment": {
            "food_code": "aimiao_soup",
            "food_label": "Ai Miao Soup",
            "rationale": {
                "internal": "do not leak",
                "weights": {"ai_trace": 3},
            },
        },
    })
    lowered = prompt.lower()

    assert "scoring" not in lowered
    assert "weights" not in lowered
    assert "food_code" not in lowered
    assert "hidden rubric" not in lowered
    assert "aimiao_soup" not in lowered
    assert "do not leak" not in lowered
    assert "艾苗汤" in prompt
    assert "Ai Miao soup" in prompt


def test_shopkeeper_reply_returns_to_required_question_before_two_answers():
    service = ShopkeeperReplyService()

    result = service.generate_reply({
        "stage": "after_required_answer",
        "participant_status": "scoring",
        "answered_count": 1,
        "total_questions": 2,
        "current_question_text": "Have you ever sincerely said thank you to AI?",
        "last_user_transcript": "我刚才其实是在开玩笑",
        "interpretation_status": "accepted",
        "assignment": None,
    })

    assert "下一题" in result["reply_text"]


def test_shopkeeper_reply_after_assigned_does_not_reinterpret_result():
    service = ShopkeeperReplyService()

    result = service.generate_reply({
        "stage": "assigned",
        "participant_status": "assigned",
        "answered_count": 2,
        "total_questions": 2,
        "current_question_text": None,
        "last_user_transcript": "为什么我是这个？",
        "interpretation_status": None,
        "assignment": {
            "food_code": "salad",
            "food_label": "Salad",
        },
    })

    assert "结果不会再改" in result["reply_text"]
    assert "沙拉 / Salad" in result["reply_text"]
    assert "因为" not in result["reply_text"]


def test_shopkeeper_ready_to_assign_uses_system_assignment_only():
    service = ShopkeeperReplyService()

    result = service.generate_reply({
        "stage": "ready_to_assign",
        "participant_status": "assigned",
        "answered_count": 2,
        "total_questions": 2,
        "assignment": {
            "food_code": "aimiao_salad",
            "food_label": "Some invented label",
        },
    })

    assert "艾苗沙拉 / Ai Miao salad" in result["reply_text"]
    assert "Some invented label" not in result["reply_text"]
    assert "不加菜单" in result["reply_text"]
