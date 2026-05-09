from __future__ import annotations

from have_some_ai.chat import ShopkeeperReplyService


class FakeReplyLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_shopkeeper_reply_service_returns_only_reply_text():
    service = ShopkeeperReplyService()

    result = service.generate_reply({
        "stage": "formal_question_1",
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
        "stage": "formal_question_2",
        "participant_status": "scoring",
        "answered_count": 1,
        "total_questions": 2,
        "current_question_text": "Have you ever sincerely said thank you to AI?",
        "last_user_transcript": "我刚才其实是在开玩笑",
        "interpretation_status": "accepted",
        "assignment": None,
    })

    assert "第二个问题" in result["reply_text"]


def test_shopkeeper_reply_uses_english_for_selected_language():
    service = ShopkeeperReplyService()

    result = service.generate_reply({
        "stage": "formal_question_1",
        "response_language": "en",
        "participant_status": "questioning",
        "answered_count": 0,
        "total_questions": 2,
        "current_question_text": "Have you ever sincerely said thank you to AI?",
        "last_user_transcript": "English",
        "interpretation_status": None,
        "assignment": None,
    })

    assert "First question" in result["reply_text"]
    assert "Have you ever sincerely said thank you to AI?" in result["reply_text"]
    assert "第一个问题" not in result["reply_text"]


def test_shopkeeper_language_gate_uses_required_prompt():
    service = ShopkeeperReplyService()

    result = service.generate_reply({
        "stage": "language_gate",
        "participant_status": "new",
        "answered_count": 0,
        "total_questions": 2,
    })

    assert result["reply_text"] == (
        "Hi! 你好！\n"
        "Would you like to continue in English or 中文"
    )


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

    assert "换下一个人吧" in result["reply_text"]
    assert "沙拉 / Salad" in result["reply_text"]
    assert "因为" not in result["reply_text"]


def test_shopkeeper_farewell_uses_system_assignment_only():
    service = ShopkeeperReplyService()

    result = service.generate_reply({
        "stage": "farewell",
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
    assert "吃完猜猜我为什么给你这个东西" in result["reply_text"]


def test_shopkeeper_freeform_not_eating_chat_uses_llm_without_echoing_template():
    llm = FakeReplyLLM(["你像是刚从一段很长的路里出来，先在这儿停一口气。"])
    service = ShopkeeperReplyService(llm_client=llm)

    result = service.generate_reply({
        "stage": "not_eating_chat",
        "participant_status": "new",
        "next_action": "not_eating_chat",
        "answered_count": 0,
        "total_questions": 2,
        "current_question_text": None,
        "last_user_transcript": "我今天有点累",
        "interpretation": {"route": "chitchat", "count": 1},
        "chat_mode": "A_NO_FOOD",
        "not_eating_chat_count": 1,
        "assignment": None,
    })

    assert result == {"reply_text": "你像是刚从一段很长的路里出来，先在这儿停一口气。"}
    assert len(llm.calls) == 1
    assert "我今天有点累" in llm.calls[0]["messages"][0]["content"]
    assert "freeform_chitchat_turn\":1" in llm.calls[0]["messages"][0]["content"]


def test_shopkeeper_formal_chitchat_uses_llm_for_first_two_turns_only():
    llm = FakeReplyLLM(["这问题听着像在问我，其实也有点像在问你。"])
    service = ShopkeeperReplyService(llm_client=llm)

    first = service.generate_reply({
        "stage": "formal_question_1",
        "participant_status": "questioning",
        "next_action": "repeat_current_question",
        "answered_count": 0,
        "total_questions": 2,
        "current_question_text": "你有没有对 AI 说过“谢谢”，而且是真心的？",
        "last_user_transcript": "你会对人说谢谢吗？",
        "interpretation": {"route": "chitchat", "count": 1},
        "formal_chitchat_count": 1,
        "assignment": None,
    })
    third = service.generate_reply({
        "stage": "formal_question_1",
        "participant_status": "questioning",
        "next_action": "repeat_current_question",
        "answered_count": 0,
        "total_questions": 2,
        "current_question_text": "你有没有对 AI 说过“谢谢”，而且是真心的？",
        "last_user_transcript": "为什么非要问这个？",
        "interpretation": {"route": "chitchat", "count": 3},
        "formal_chitchat_count": 3,
        "assignment": None,
    })

    assert first["reply_text"] == "这问题听着像在问我，其实也有点像在问你。"
    assert "回到这题" in third["reply_text"]
    assert len(llm.calls) == 1


def test_shopkeeper_freeform_llm_failure_falls_back_to_template():
    llm = FakeReplyLLM([""])
    service = ShopkeeperReplyService(llm_client=llm)

    result = service.generate_reply({
        "stage": "not_eating_chat",
        "participant_status": "new",
        "next_action": "not_eating_chat",
        "answered_count": 0,
        "total_questions": 2,
        "current_question_text": None,
        "last_user_transcript": "我今天有点累",
        "interpretation": {"route": "chitchat", "count": 1},
        "chat_mode": "A_NO_FOOD",
        "not_eating_chat_count": 1,
        "assignment": None,
    })

    assert result["reply_text"] == "嗯，我今天有点累。不吃也行，就当路过这家店。"
