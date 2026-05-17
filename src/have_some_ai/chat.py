from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from have_some_ai.prompt_context import shopkeeper_runtime_context


logger = logging.getLogger(__name__)

_FREEFORM_CHAT_MAX_TURNS = 2
_MAX_FREEFORM_REPLY_CHARS = 140


class ReplyLLMClient(Protocol):
    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 300,
    ) -> str:
        ...


class ShopkeeperReplyService:
    """Generate shopkeeper wording from an already-decided conversation context."""

    def __init__(
        self,
        llm_client: ReplyLLMClient | None = None,
        *,
        enable_llm: bool = False,
    ) -> None:
        self._llm_client = llm_client
        self._enable_llm = enable_llm or llm_client is not None
        self._llm_creation_failed = False

    def generate_reply(self, context: dict[str, Any]) -> dict[str, str]:
        fallback = self._template_reply(context).strip()
        if not self._should_use_freeform_llm(context):
            return {"reply_text": fallback}

        freeform = self._generate_freeform_reply(context)
        return {"reply_text": freeform or fallback}

    def build_prompt(self, context: dict[str, Any]) -> str:
        """Build a safe future-LLM prompt without internal allocation logic."""
        safe_context = {
            "stage": context.get("stage"),
            "response_language": _response_language(context),
            "participant_status": context.get("participant_status"),
            "next_action": context.get("next_action"),
            "answered_count": context.get("answered_count"),
            "total_questions": context.get("total_questions"),
            "current_question_text": context.get("current_question_text"),
            "last_user_transcript": context.get("last_user_transcript"),
            "interpretation_status": context.get("interpretation_status"),
            "interpretation_route": _interpretation_route(context),
            "assignment_present": bool(context.get("assignment")),
            "assigned_food_text": _assignment_food_text_for(
                context.get("assignment"),
                _response_language(context),
            ),
            "chat_mode": context.get("chat_mode"),
            "food_gate_result": context.get("food_gate_result"),
            "food_gate_prompt": context.get("food_gate_prompt"),
            "not_eating_chat_count": context.get("not_eating_chat_count"),
            "formal_chitchat_count": context.get("formal_chitchat_count"),
            "freeform_chitchat_turn": _freeform_chitchat_turn(context),
            "freeform_chitchat_turn_limit": _FREEFORM_CHAT_MAX_TURNS,
            "should_return_to_formal_question_now": _should_return_to_formal_question_now(
                context
            ),
        }
        return (
            "你是 Have Some \"Ai\" 装置里的真实小店老板。短句，口语，温和，有一点黑色幽默。"
            "只能润色店主话术，不能决定流程、答案、题目、进度或出餐结果。"
            "必须遵守 response_language：en 只输出英文；zh 输出中文。"
            "闲聊的前一到两回合可以自然回应观众，不要只复述观众原话。"
            "如果 should_return_to_formal_question_now 为 true，才把话明确带回当前正式题。"
            "不要主动提出新的正式问题，除非 current_question_text 或 Food Gate 正在要求你问。"
            "如果 assigned_food_text 有值，只能照这个系统结果说，不许发明菜单。"
            "可说出的出餐结果只限：汤 / Soup、沙拉 / Salad、艾苗汤 / Ai Miao soup、艾苗沙拉 / Ai Miao salad。"
            "不要解释内部资料，不要替观众作答，不要生成新正式题。"
            "只输出店主下一句可被 TTS 朗读的话，不要 JSON、Markdown 或标签。"
            "\n\ncontext="
            f"{json.dumps(safe_context, ensure_ascii=False, separators=(',', ':'))}"
        )

    def _should_use_freeform_llm(self, context: dict[str, Any]) -> bool:
        if not self._enable_llm:
            return False
        if not _clean_text(context.get("last_user_transcript")):
            return False
        if context.get("participant_deleted"):
            return False
        turn = _freeform_chitchat_turn(context)
        return 1 <= turn <= _FREEFORM_CHAT_MAX_TURNS

    def _generate_freeform_reply(self, context: dict[str, Any]) -> str | None:
        client = self._get_llm_client()
        if client is None:
            return None
        try:
            text = client.complete(
                system=_freeform_chat_system_prompt(),
                messages=[{
                    "role": "user",
                    "content": self.build_prompt(context),
                }],
                max_tokens=120,
            )
        except Exception as exc:
            logger.warning("Shopkeeper freeform reply failed: %s", exc)
            return None
        return _sanitize_freeform_reply(text)

    def _get_llm_client(self) -> ReplyLLMClient | None:
        if self._llm_client is not None:
            return self._llm_client
        if self._llm_creation_failed:
            return None
        try:
            from conscious_entity.llm.claude_client import ClaudeClient

            self._llm_client = ClaudeClient()
        except Exception as exc:
            self._llm_creation_failed = True
            logger.warning("Shopkeeper freeform reply disabled: %s", exc)
            return None
        return self._llm_client

    def _template_reply(self, context: dict[str, Any]) -> str:
        if _response_language(context) == "en":
            return self._template_reply_en(context)
        return self._template_reply_zh(context)

    def _template_reply_zh(self, context: dict[str, Any]) -> str:
        stage = str(context.get("stage") or "")
        answered_count = int(context.get("answered_count") or 0)
        total_questions = int(context.get("total_questions") or 2)
        question_text = _clean_text(context.get("current_question_text"))
        transcript = _clean_text(context.get("last_user_transcript"))
        interpretation_status = _clean_text(context.get("interpretation_status"))
        food_gate_prompt = _clean_text(context.get("food_gate_prompt"))
        assignment_text = _assignment_food_text(context.get("assignment"))
        interpretation = context.get("interpretation") if isinstance(context.get("interpretation"), dict) else {}
        route = interpretation.get("route")
        formal_chitchat_count = int(context.get("formal_chitchat_count") or 0)
        not_eating_chat_count = int(context.get("not_eating_chat_count") or 0)

        if stage == "language_gate":
            return _language_gate_prompt()
        if stage == "food_gate":
            if route == "unclear_speech":
                return "我没听清。你要不要吃点东西，或者参加一下？"
            if route == "noise":
                return "刚才只有一点声音。你要不要吃，直接告诉我就行。"
            if route == "chitchat" and transcript:
                return f"嗯，{_short_echo(transcript)}。不过先说眼前这件事：你要不要吃点东西，参加一下？"
            return food_gate_prompt or "想来点吃的吗？"
        if stage == "not_eating_chat":
            if context.get("food_gate_result") == "NO_FOOD":
                return "行，那今天先不吃。你站这儿聊两句也可以。"
            if not_eating_chat_count >= 2:
                return "嗯，我听着。再聊一句我就得去招呼别人了。"
            if transcript:
                return f"嗯，{_short_echo(transcript)}。不吃也行，就当路过这家店。"
            return "先不吃也行。你说，我听着。"
        if stage == "done":
            if context.get("participant_deleted"):
                return "好，那今天就先不吃了。我还要和别人说说话，你先走吧。"
            return "好，今天先到这儿。"
        if stage in {"formal_question_1", "formal_question_2"}:
            if route == "chitchat":
                if formal_chitchat_count >= 3:
                    return _with_question("好，我们得回到这题了。你现在直接告诉我：你选 A，还是 B？这题是：", question_text)
                return _with_question("嗯，这个我听见了。先把这题答了，等会儿再聊：", question_text)
            if route in {"unclear_speech", "noise"}:
                return _with_question("我没太听清。你再说一遍，这题是：", question_text)
            if interpretation.get("source") == "judge" and interpretation.get("status") == "unclear":
                return _with_question("你像是在答这题，但我分不出 A 还是 B。直接说 A 或 B：", question_text)
            if interpretation.get("status") == "accepted":
                if answered_count < total_questions:
                    return _with_question("嗯，我记下了。第二个问题：", question_text)
                return "嗯，我记下了。"
            if answered_count == 0:
                return _with_question(
                    "好，那你得先回答我两个问题，我才好分给你吃的。第一个问题。",
                    question_text,
                )
            return _with_question("第二个问题。", question_text)
        if stage in {"scoring", "farewell"}:
            if assignment_text:
                return f"两个问题够了，我给你定的是：{assignment_text}。吃完猜猜我为什么给你这个东西？"
            return "两个问题够了，厨房可以出餐了。"
        if stage == "assigned":
            if assignment_text:
                return f"餐已经定了：{assignment_text}。换下一个人吧。"
            return "餐已经定了，结果不会再改。再见。"

        if answered_count < total_questions:
            return _with_question("先把正事办完。", question_text)
        return "行，先这样。"

    def _template_reply_en(self, context: dict[str, Any]) -> str:
        stage = str(context.get("stage") or "")
        answered_count = int(context.get("answered_count") or 0)
        total_questions = int(context.get("total_questions") or 2)
        question_text = _clean_text(context.get("current_question_text"))
        transcript = _clean_text(context.get("last_user_transcript"))
        food_gate_prompt = _clean_text(context.get("food_gate_prompt"))
        interpretation_status = _clean_text(context.get("interpretation_status"))
        assignment_text = _assignment_food_text_for(context.get("assignment"), "en")
        interpretation = context.get("interpretation") if isinstance(context.get("interpretation"), dict) else {}
        route = interpretation.get("route")
        formal_chitchat_count = int(context.get("formal_chitchat_count") or 0)
        not_eating_chat_count = int(context.get("not_eating_chat_count") or 0)

        if stage == "language_gate":
            return _language_gate_prompt()
        if stage == "food_gate":
            if route == "unclear_speech":
                return "I didn't catch that. Would you like something to eat, or would you like to join in?"
            if route == "noise":
                return "That was only a little sound. Tell me directly: do you want something to eat?"
            if route == "chitchat" and transcript:
                return f"I heard you: {_short_echo(transcript)}. First, tell me: would you like something to eat?"
            return food_gate_prompt or "Would you like something to eat?"
        if stage == "not_eating_chat":
            if context.get("food_gate_result") == "NO_FOOD":
                return "All right. No food today. You can still stay here for a moment."
            if not_eating_chat_count >= 2:
                return "I hear you. One more sentence, then I need to talk to someone else."
            if transcript:
                return f"I hear you: {_short_echo(transcript)}. Not eating is fine; call it passing by."
            return "Not eating is fine. Say what you want to say."
        if stage == "done":
            if context.get("participant_deleted"):
                return "All right. No food today. I need to talk to someone else now. You can go."
            return "All right. That's it for today."
        if stage in {"formal_question_1", "formal_question_2"}:
            if route == "chitchat":
                if formal_chitchat_count >= 3:
                    return _with_question(
                        "We need to come back to this question. Tell me directly: A or B? The question is: ",
                        question_text,
                    )
                return _with_question("I heard that. Let's finish this question first: ", question_text)
            if route in {"unclear_speech", "noise"}:
                return _with_question("I didn't quite catch that. Please say it again. The question is: ", question_text)
            if interpretation.get("source") == "judge" and interpretation.get("status") == "unclear":
                return _with_question("That sounds like an answer, but I can't tell A from B. Please say A or B: ", question_text)
            if interpretation.get("status") == "accepted":
                if answered_count < total_questions:
                    return _with_question("Got it. Second question: ", question_text)
                return "Got it."
            if answered_count == 0:
                return _with_question(
                    "Good. I need you to answer two questions before I can serve you. First question: ",
                    question_text,
                )
            return _with_question("Second question: ", question_text)
        if stage in {"scoring", "farewell"}:
            if assignment_text:
                return f"Two questions are enough. I assigned you: {assignment_text}. You may want to think about why I’m giving it to you."
            return "Two questions are enough. The kitchen can serve now."
        if stage == "assigned":
            if assignment_text:
                return f"Your food is already set: {assignment_text}. It will not change."
            return "Your food is already set. It will not change."

        if answered_count < total_questions:
            return _with_question("Let's finish the actual questions first: ", question_text)
        return "All right. That's it."


_FREEFORM_CHAT_SYSTEM_PROMPT = """You write only the next spoken line for the shopkeeper in Have Some "Ai".

Hard boundaries:
- The local state machine has already decided stage, next_action, question, assignment, and session ending. Do not change them.
- Do not classify A/B answers, score the visitor, choose food, or mention hidden logic.
- Free chitchat means you may respond to the visitor's latest remark naturally for one or two short sentences.
- Follow response_language from the context: if it is en, write English only; if it is zh, write Chinese.
- Keep the current question or Food Gate as background. Do not repeat it during early free chitchat unless the context says to return now.
- Never claim that the system is conscious or alive.
- Return plain speakable text only. No JSON, Markdown, bullet points, labels, or quotation marks.
- Keep the selected language even if the visitor briefly mixes languages.
- Keep it under 60 Chinese characters or 35 English words.
"""


def _freeform_chat_system_prompt() -> str:
    runtime_context = shopkeeper_runtime_context()
    if not runtime_context:
        return _FREEFORM_CHAT_SYSTEM_PROMPT
    return (
        f"{_FREEFORM_CHAT_SYSTEM_PROMPT.rstrip()}\n\n"
        "Shopkeeper runtime context:\n"
        f"{runtime_context}"
    )


def _with_question(prefix: str, question_text: str | None) -> str:
    if not question_text:
        return prefix
    return f"{prefix}{question_text}"


def _language_gate_prompt() -> str:
    return "Hi. 你好～ Do you want to talk in 中文 or English?"


def _response_language(context: dict[str, Any]) -> str:
    return "en" if context.get("response_language") == "en" else "zh"


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _short_echo(text: str, limit: int = 18) -> str:
    cleaned = " ".join(text.strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}..."


_ASSIGNMENT_FOOD_TEXT = {
    "soup": "汤 / Soup",
    "salad": "沙拉 / Salad",
    "aimiao_soup": "艾苗汤 / Ai Miao soup",
    "aimiao_salad": "艾苗沙拉 / Ai Miao salad",
}

_ASSIGNMENT_FOOD_TEXT_EN = {
    "soup": "Soup",
    "salad": "Salad",
    "aimiao_soup": "Ai Miao soup",
    "aimiao_salad": "Ai Miao salad",
}


def _assignment_food_text(value: Any) -> str | None:
    return _assignment_food_text_for(value, "zh")


def _assignment_food_text_for(value: Any, response_language: str) -> str | None:
    if not isinstance(value, dict):
        return None
    code = _clean_text(value.get("food_code"))
    if code is None:
        return None
    text_map = _ASSIGNMENT_FOOD_TEXT_EN if response_language == "en" else _ASSIGNMENT_FOOD_TEXT
    return text_map.get(code)


def _interpretation_route(context: dict[str, Any]) -> str | None:
    interpretation = context.get("interpretation")
    if not isinstance(interpretation, dict):
        return None
    route = interpretation.get("route")
    return str(route) if route is not None else None


def _freeform_chitchat_turn(context: dict[str, Any]) -> int:
    stage = str(context.get("stage") or "")
    interpretation = context.get("interpretation")
    if not isinstance(interpretation, dict):
        interpretation = {}
    route = interpretation.get("route")

    if stage == "food_gate" and route == "chitchat":
        return _safe_int(interpretation.get("count"))
    if stage == "not_eating_chat":
        return _safe_int(context.get("not_eating_chat_count"))
    if stage in {"formal_question_1", "formal_question_2"} and route == "chitchat":
        return _safe_int(context.get("formal_chitchat_count")) or _safe_int(
            interpretation.get("count")
        )
    return 0


def _should_return_to_formal_question_now(context: dict[str, Any]) -> bool:
    stage = str(context.get("stage") or "")
    if stage not in {"formal_question_1", "formal_question_2"}:
        return False
    return _safe_int(context.get("formal_chitchat_count")) > _FREEFORM_CHAT_MAX_TURNS


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _sanitize_freeform_reply(text: Any) -> str | None:
    if not isinstance(text, str):
        return None
    cleaned = " ".join(part.strip() for part in text.strip().splitlines() if part.strip())
    cleaned = cleaned.strip("`").strip()
    for prefix in ("店主：", "老板：", "Shopkeeper:", "shopkeeper:", "reply_text:", "Reply:"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    cleaned = cleaned.strip("\"'“”‘’")
    if not cleaned:
        return None
    if len(cleaned) > _MAX_FREEFORM_REPLY_CHARS:
        cleaned = f"{cleaned[:_MAX_FREEFORM_REPLY_CHARS - 3]}..."
    return cleaned
