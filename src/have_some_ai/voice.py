from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from conscious_entity.llm.claude_client import ClaudeClient
from have_some_ai.models import Question


@dataclass(frozen=True)
class RubricInterpretation:
    option_id: str | None
    confidence: float
    reason_zh: str
    reason_en: str
    detected_language: str | None
    raw_json: dict[str, Any] = field(default_factory=dict)
    route: str = "answer"


@dataclass(frozen=True)
class FoodGateIntentInterpretation:
    route: str
    confidence: float
    rationale: str
    detected_language: str | None
    raw_json: dict[str, Any] = field(default_factory=dict)


class RubricInterpreter(Protocol):
    def interpret(
        self,
        *,
        question: Question,
        transcript: str,
        detected_language: str | None = None,
    ) -> RubricInterpretation:
        ...


class FoodGateIntentInterpreter(Protocol):
    def interpret_food_gate(
        self,
        *,
        food_gate_prompt: str,
        transcript: str,
        response_language: str | None,
        local_fallback_route: str,
    ) -> FoodGateIntentInterpretation | None:
        ...


class ClaudeRubricInterpreter:
    def __init__(self, llm_client: ClaudeClient | None = None) -> None:
        self._llm_client = llm_client

    def interpret(
        self,
        *,
        question: Question,
        transcript: str,
        detected_language: str | None = None,
    ) -> RubricInterpretation:
        client = self._llm_client or ClaudeClient()
        text = client.complete(
            system=_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": _user_prompt(question, transcript, detected_language),
            }],
            max_tokens=300,
        )
        valid_options = {option.id for option in question.options}
        try:
            payload = _extract_json(text)
        except ValueError as parse_error:
            try:
                repair_text = client.complete(
                    system=_REPAIR_SYSTEM_PROMPT,
                    messages=[{
                        "role": "user",
                        "content": _repair_prompt(text),
                    }],
                    max_tokens=220,
                )
                payload = _extract_json(repair_text)
                payload["_json_repaired"] = True
            except Exception as repair_error:
                return _unclear_interpretation(
                    detected_language=detected_language,
                    reason=(
                        "The answer could not be interpreted because the rubric JSON "
                        "was malformed; please try again."
                    ),
                    raw_json={
                        "status": "unclear",
                        "parse_error": str(parse_error),
                        "repair_error": str(repair_error),
                    },
                )

        return _interpret_payload(payload, valid_options, detected_language)


ClaudeRubricJudge = ClaudeRubricInterpreter


class ClaudeFoodGateIntentInterpreter:
    def __init__(
        self,
        llm_client: ClaudeClient | None = None,
        *,
        min_confidence: float = 0.55,
    ) -> None:
        self._llm_client = llm_client
        self._min_confidence = min_confidence

    def interpret_food_gate(
        self,
        *,
        food_gate_prompt: str,
        transcript: str,
        response_language: str | None,
        local_fallback_route: str,
    ) -> FoodGateIntentInterpretation | None:
        client = self._llm_client or ClaudeClient()
        try:
            text = client.complete(
                system=_FOOD_GATE_SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": _food_gate_user_prompt(
                        food_gate_prompt=food_gate_prompt,
                        transcript=transcript,
                        response_language=response_language,
                        local_fallback_route=local_fallback_route,
                    ),
                }],
                max_tokens=180,
            )
            payload = _extract_json(text)
        except Exception:
            return None

        return _interpret_food_gate_payload(
            payload,
            min_confidence=self._min_confidence,
            response_language=response_language,
        )


_SYSTEM_PROMPT = """You are a strict formal-question turn judge for Have Some "Ai".

Rules:
- Return compact valid JSON only. Do not use Markdown. Do not wrap in code fences.
- Do not add explanations outside the JSON.
- This function is called only after the local FormalTurnRouter has classified
  the transcript as needing formal-question judgment.
- First decide route:
  - route answer: the visitor is trying to answer the current formal question,
    even if the wording is soft, hesitant, indirect, or incomplete.
  - route chitchat: the visitor is talking about something unrelated to the
    current formal question, asking the shopkeeper/system a side question, or
    making a comment instead of answering.
- If route is chitchat, set label to null, status to chitchat, and do not map it
  to A/B/unclear.
- If route is answer, judge whether the answer clearly corresponds to option A
  or option B.
- Return label A or B when the transcript directly names A/B or clearly matches
  the visible option text/meaning. Short affirmative/negative answers such as
  "有吧", "应该有", "我觉得有", "算是", "没有吧", "应该没有", "我觉得没有",
  "好", "行", "可以", "yes", "ok", "sure", "probably yes", "no", or
  "probably not" should be mapped to A or B when the visible choices make that
  mapping clear.
- Return label unclear only when route is answer but the answer mentions both A
  and B, says C/Other, refuses to choose, says "都行", "可能吧", "不知道", or
  cannot be mapped to exactly one visible option.
- Do not infer hidden preferences beyond the transcript and visible options.
- Do not chat, advance the flow, generate shopkeeper replies, score, or assign food.
- Do not decide the food assignment.
- If the answer is unclear, return label unclear with low confidence.
- Support Chinese, English, and mixed Chinese-English transcripts.
- confidence must be between 0 and 1.
- rationale must be one short sentence for logs only.

Accepted example:
{"route":"answer","label":"A","status":"accepted","confidence":0.86,"rationale":"The visitor clearly said A.","detected_language":"zh"}

Unclear example:
{"route":"answer","label":"unclear","status":"unclear","confidence":0.2,"rationale":"The visitor is answering but did not clearly choose A or B.","detected_language":"unknown"}

Chitchat example:
{"route":"chitchat","label":null,"status":"chitchat","confidence":0.85,"rationale":"The visitor is commenting on the machine, not answering the formal question.","detected_language":"zh"}
"""


_FOOD_GATE_SYSTEM_PROMPT = """You are a strict Food Gate entry-intent classifier for Have Some "Ai".

Rules:
- Return compact valid JSON only. Do not use Markdown. Do not wrap in code fences.
- Do not add explanations outside the JSON.
- You only decide the visitor's entry intent for the Food Gate prompt, which asks
  whether they want something to eat or want to talk.
- Use route want_food when the visitor is asking for food, agreeing to eat, or
  accepting the food path. This includes soft or colloquial Chinese such as
  "吃点吧", "吃点儿吧", "那吃点吧", "来点吧", "想吃点", "整点吃的", and English
  like "I want food", "something to eat", or "I'm hungry".
- Use route want_chat when the visitor wants to talk, asks a side question,
  comments on the project/shopkeeper, or asks for an explanation.
- Use route no_food when the visitor rejects eating and is not asking to talk.
  If the visitor rejects food but asks to talk, use want_chat.
- Use route unclear_speech only for filler, noise, empty-like utterances, or text
  that is too unclear to choose food/chat/no_food.
- Do not answer the visitor. Do not chat. Do not ask formal questions.
- Do not map to A/B, score, write answers, advance formal questions, or assign food.
- Do not use shopkeeper runtime context or invent menu items.
- Support Chinese, English, and mixed Chinese-English transcripts.
- confidence must be between 0 and 1.
- rationale must be one short sentence for logs only.

Accepted examples:
{"route":"want_food","confidence":0.91,"rationale":"The visitor said they want to eat a little.","detected_language":"zh"}
{"route":"want_chat","confidence":0.88,"rationale":"The visitor is asking a side question instead of asking for food.","detected_language":"zh"}
{"route":"no_food","confidence":0.9,"rationale":"The visitor clearly declined food.","detected_language":"en"}
{"route":"unclear_speech","confidence":0.3,"rationale":"The utterance is only a filler sound.","detected_language":"unknown"}
"""


_REPAIR_SYSTEM_PROMPT = """Convert malformed rubric output into compact valid JSON only.

Rules:
- Do not reinterpret the visitor answer.
- Preserve the original meaning as much as possible.
- Return one JSON object only.
- Do not use Markdown, code fences, or explanations.
- Use route as answer or chitchat.
- Use status as accepted, unclear, or chitchat.
- Use label as A, B, unclear, or null.
- Use confidence as a number between 0 and 1.
- Use rationale as a string.
"""


def _user_prompt(
    question: Question,
    transcript: str,
    detected_language: str | None,
) -> str:
    options = [
        {
            "id": option.id,
            "text_en": option.text,
            "text_zh": option.text_zh or "",
        }
        for option in question.options
    ]
    options_by_id = {option["id"]: option for option in options}
    payload = {
        "question": {
            "id": question.id,
            "text_en": question.text,
            "text_zh": question.text_zh or "",
        },
        "visible_choices": {
            "A": options_by_id.get("A"),
            "B": options_by_id.get("B"),
        },
        "scoring_options": options,
        "visitor_transcript": transcript,
        "stt_detected_language": detected_language,
    }
    return json.dumps(payload, ensure_ascii=False)


def _food_gate_user_prompt(
    *,
    food_gate_prompt: str,
    transcript: str,
    response_language: str | None,
    local_fallback_route: str,
) -> str:
    return json.dumps(
        {
            "food_gate_prompt": food_gate_prompt,
            "visitor_transcript": transcript,
            "response_language": response_language,
            "local_fallback_route": local_fallback_route,
            "allowed_routes": [
                "want_food",
                "want_chat",
                "no_food",
                "unclear_speech",
            ],
        },
        ensure_ascii=False,
    )


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    payload = _try_json_object(stripped)
    if payload is None:
        unfenced = _strip_code_fences(stripped)
        payload = _try_json_object(unfenced)
    if payload is None:
        balanced = _first_balanced_json_object(stripped)
        if balanced is None:
            raise ValueError("LLM rubric output did not contain JSON")
        payload = _try_json_object(balanced)
    if payload is None:
        raise ValueError("LLM rubric output was not valid JSON")
    if not isinstance(payload, dict):
        raise ValueError("LLM rubric output must be a JSON object")
    return payload


def _try_json_object(text: str) -> dict[str, Any] | None:
    for candidate in (text, _remove_trailing_commas(text)):
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
        raise ValueError("LLM rubric output must be a JSON object")
    return None


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _first_balanced_json_object(text: str) -> str | None:
    start = None
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(text):
        if start is None:
            if char == "{":
                start = index
                depth = 1
            continue

        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return None


def _remove_trailing_commas(text: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", text)


def _repair_prompt(malformed_output: str) -> str:
    return json.dumps(
        {
            "malformed_output": malformed_output,
            "required_shape": {
                "route": "answer or chitchat",
                "label": "A, B, or unclear",
                "status": "accepted, unclear, or chitchat",
                "confidence": "number between 0 and 1",
                "rationale": "string",
                "detected_language": "zh, en, mixed, or unknown",
            },
        },
        ensure_ascii=False,
    )


def _interpret_payload(
    payload: dict[str, Any],
    valid_options: set[str],
    detected_language: str | None,
) -> RubricInterpretation:
    confidence = _coerce_confidence(payload.get("confidence"))
    route = _normalize_route(payload.get("route"), payload.get("status"))
    label = _normalize_label(payload.get("label", payload.get("option_id")))
    option_id = label if label in {"A", "B"} else None
    status = str(payload.get("status") or "").strip().lower()
    if status not in {"accepted", "unclear", "chitchat"}:
        status = "accepted" if option_id else "unclear"
    if route == "chitchat" and option_id is None:
        status = "chitchat"
    if option_id is not None:
        route = "answer"
        if status == "chitchat":
            status = "accepted"
    if route != "chitchat" and status == "chitchat":
        status = "accepted" if option_id else "unclear"

    if option_id is not None and option_id not in valid_options:
        option_id = None
        status = "unclear"
        route = "answer"
    if status == "accepted" and option_id is None:
        status = "unclear"
        route = "answer"
    if status == "unclear" or confidence < 0.55:
        option_id = None
        status = "chitchat" if route == "chitchat" else "unclear"

    reason = str(payload.get("rationale") or payload.get("reason") or "").strip()
    default_reason_zh = (
        "我听见了，但这不像是在答这题。"
        if route == "chitchat"
        else "没太听清，请再说一遍。"
    )
    default_reason_en = (
        "The visitor is not answering the current formal question."
        if route == "chitchat"
        else "The answer is unclear; please try again."
    )
    reason_zh = str(payload.get("reason_zh") or reason or default_reason_zh)
    reason_en = str(payload.get("reason_en") or reason or default_reason_en)
    normalized = dict(payload)
    normalized["route"] = route
    normalized["label"] = option_id or ("unclear" if route == "answer" else None)
    normalized["status"] = status
    normalized["option_id"] = option_id
    normalized["confidence"] = confidence
    if reason:
        normalized["rationale"] = reason
        normalized["reason"] = reason

    return RubricInterpretation(
        option_id=option_id,
        confidence=confidence,
        reason_zh=reason_zh,
        reason_en=reason_en,
        detected_language=(
            str(payload.get("detected_language"))
            if payload.get("detected_language")
            else detected_language
        ),
        raw_json=normalized,
        route=route,
    )


def _interpret_food_gate_payload(
    payload: dict[str, Any],
    *,
    min_confidence: float,
    response_language: str | None,
) -> FoodGateIntentInterpretation | None:
    route = _normalize_food_gate_route(payload.get("route"))
    confidence = _coerce_confidence(payload.get("confidence"))
    if route is None or confidence < min_confidence:
        return None

    rationale = str(payload.get("rationale") or payload.get("reason") or "").strip()
    normalized = dict(payload)
    normalized["route"] = route
    normalized["confidence"] = confidence
    if rationale:
        normalized["rationale"] = rationale

    return FoodGateIntentInterpretation(
        route=route,
        confidence=confidence,
        rationale=rationale,
        detected_language=(
            str(payload.get("detected_language"))
            if payload.get("detected_language")
            else response_language
        ),
        raw_json=normalized,
    )


def _unclear_interpretation(
    *,
    detected_language: str | None,
    reason: str,
    raw_json: dict[str, Any],
) -> RubricInterpretation:
    return RubricInterpretation(
        option_id=None,
        confidence=0.0,
        reason_zh="没太听清，请再说一遍。",
        reason_en=reason,
        detected_language=detected_language,
        raw_json=raw_json,
        route="answer",
    )


def _normalize_route(route_value: Any, status_value: Any) -> str:
    value = str(route_value or status_value or "").strip().lower()
    if value in {"chitchat", "chat", "side_chat", "sidechat", "out_of_scope", "not_answer"}:
        return "chitchat"
    return "answer"


def _normalize_food_gate_route(value: Any) -> str | None:
    normalized = str(value or "").strip().lower().replace("-", "_")
    compact = normalized.replace("_", "")
    if compact in {
        "wantfood",
        "food",
        "eat",
        "wanteat",
        "wanttoeat",
        "wantsfood",
        "wantsomethingtoeat",
        "hungry",
    }:
        return "want_food"
    if compact in {
        "wantchat",
        "chat",
        "talk",
        "wanttalk",
        "wanttotalk",
        "talkonly",
        "question",
        "sidequestion",
    }:
        return "want_chat"
    if compact in {
        "nofood",
        "notfood",
        "noeat",
        "noteat",
        "declinefood",
        "refusefood",
        "decline",
    }:
        return "no_food"
    if compact in {"unclearspeech", "unclear", "noise", "unknown", "filler"}:
        return "unclear_speech"
    return None


def _normalize_label(value: Any) -> str:
    if value is None:
        return "unclear"
    normalized = str(value).strip()
    if not normalized or normalized.lower() in {"null", "none"}:
        return "unclear"
    normalized = normalized.upper()
    return normalized if normalized in {"A", "B"} else "unclear"


def _coerce_confidence(value: Any) -> float:
    try:
        return _clamp(float(value), 0.0, 1.0)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
