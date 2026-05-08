from __future__ import annotations

import json
from typing import Any


class ShopkeeperReplyService:
    """Generate shopkeeper wording from an already-decided conversation context."""

    def generate_reply(self, context: dict[str, Any]) -> dict[str, str]:
        return {"reply_text": self._template_reply(context).strip()}

    def build_prompt(self, context: dict[str, Any]) -> str:
        """Build a safe future-LLM prompt without internal allocation logic."""
        safe_context = {
            "stage": context.get("stage"),
            "participant_status": context.get("participant_status"),
            "answered_count": context.get("answered_count"),
            "total_questions": context.get("total_questions"),
            "current_question_text": context.get("current_question_text"),
            "last_user_transcript": context.get("last_user_transcript"),
            "interpretation_status": context.get("interpretation_status"),
            "assignment_present": bool(context.get("assignment")),
            "assigned_food_text": _assignment_food_text(context.get("assignment")),
            "chat_mode": context.get("chat_mode"),
            "food_gate_result": context.get("food_gate_result"),
            "food_chat_detour_count": context.get("food_chat_detour_count"),
        }
        return (
            "你是一个真实小店老板。短句，口语，温和，有一点黑色幽默。"
            "只能润色店主话术，不能决定流程、答案、题目、进度或出餐结果。"
            "如果正式题没答完，必须把话带回当前正式题。"
            "不要主动提出新问题，除非 current_question_text 或 Food Gate 正在要求你问。"
            "如果 assigned_food_text 有值，只能照这个系统结果说，不许发明菜单。"
            "可说出的出餐结果只限：汤 / Soup、沙拉 / Salad、艾苗汤 / Ai Miao soup、艾苗沙拉 / Ai Miao salad。"
            "不要解释内部评分资料，不要替观众作答，不要生成新正式题。"
            "\n\ncontext="
            f"{json.dumps(safe_context, ensure_ascii=False, separators=(',', ':'))}"
        )

    def _template_reply(self, context: dict[str, Any]) -> str:
        stage = str(context.get("stage") or "")
        answered_count = int(context.get("answered_count") or 0)
        total_questions = int(context.get("total_questions") or 2)
        question_text = _clean_text(context.get("current_question_text"))
        transcript = _clean_text(context.get("last_user_transcript"))
        interpretation_status = _clean_text(context.get("interpretation_status"))
        food_gate_prompt = _clean_text(context.get("food_gate_prompt"))
        assignment_text = _assignment_food_text(context.get("assignment"))

        if stage == "food_gate":
            return food_gate_prompt or "想来点吃的吗？"
        if stage == "food_gate_clarify":
            return "所以你是想来点吃的，还是先不吃？"
        if stage == "free_chat":
            if context.get("food_gate_result") == "NO_FOOD":
                return "行，那先不吃。我们随便聊两句也可以。"
            if context.get("food_gate_result") == "UNCLEAR":
                return "那我先当你不吃。别紧张，聊天不用排队。"
            if transcript:
                return "嗯，我听见了。先不吃也行，我们就聊两句。"
            return "先不吃也行。你说，我听着。"
        if stage == "asking_required_question":
            if answered_count == 0:
                return _with_question(
                    "好，那你得先回答我两个问题，我才好分给你吃的。第一个问题。",
                    question_text,
                )
            return _with_question("第二个问题。", question_text)
        if stage == "awaiting_required_answer":
            if context.get("interpretation") == {"status": "continue_ack"}:
                return _with_question("那你先回答这题。", question_text)
            if interpretation_status and interpretation_status != "accepted":
                return _with_question("我没太听清。你再说一遍，这题是：", question_text)
            return _with_question("这题你直接说就行。别紧张，锅还没开。", question_text)
        if stage == "after_required_answer":
            prefix = "嗯，我记下了。"
            if transcript:
                prefix = "嗯，我记下了。你这句挺有意思。"
            if answered_count < total_questions:
                return f"{prefix} 下一题别跑。"
            return prefix
        if stage == "food_chat_detour":
            return _with_question("这个可以等会儿聊。先把这题答了：", question_text)
        if stage == "food_chat_limit":
            return _with_question("不聊那么多了，你先回答我的问题。", question_text)
        if stage == "ready_to_assign":
            if assignment_text:
                return f"两个问题够了，系统给你定的是：{assignment_text}。我只照这个出，不加菜单。"
            return "两个问题够了，厨房可以出餐了。命运已经下锅。"
        if stage == "assigned":
            if assignment_text:
                return f"餐已经定了：{assignment_text}。结果不会再改。"
            return "餐已经定了，结果不会再改。锅比我还固执。"

        if answered_count < total_questions:
            return _with_question("先把正事办完。", question_text)
        return "行，先这样。"


def _with_question(prefix: str, question_text: str | None) -> str:
    if not question_text:
        return prefix
    return f"{prefix}{question_text}"


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


_ASSIGNMENT_FOOD_TEXT = {
    "soup": "汤 / Soup",
    "salad": "沙拉 / Salad",
    "aimiao_soup": "艾苗汤 / Ai Miao soup",
    "aimiao_salad": "艾苗沙拉 / Ai Miao salad",
}


def _assignment_food_text(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    code = _clean_text(value.get("food_code"))
    if code is None:
        return None
    return _ASSIGNMENT_FOOD_TEXT.get(code)
