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


class RubricInterpreter(Protocol):
    def interpret(
        self,
        *,
        question: Question,
        transcript: str,
        detected_language: str | None = None,
    ) -> RubricInterpretation:
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


_SYSTEM_PROMPT = """You map a visitor's spoken answer to one scoring rubric option.

Rules:
- Return compact valid JSON only. Do not use Markdown. Do not wrap in code fences.
- Do not add explanations outside the JSON.
- The screen shows visible choices A, B, and C.
- A and B are scoring options. C means Other / free answer.
- Choose option_id A or B only when the answer is clear enough.
- Use option_id null and status unclear when the transcript is empty, too short,
  mostly filler, or clearly indicates the system did not hear the visitor.
- If the visitor explicitly says A, map to option_id A.
- If the visitor explicitly says B, map to option_id B.
- If the visitor says C/Other or gives a free answer, infer whether the meaning is closer to A or B.
- If the visitor only says C/Other without any content, return unclear.
- Do not decide the food assignment.
- If the answer is unclear, return option_id null with low confidence.
- Support Chinese, English, and mixed Chinese-English transcripts.
- confidence must be between 0 and 1.
- Include spoken_choice as A, B, C, freeform, or unclear.
- Include status as accepted or unclear.

Accepted example:
{"status":"accepted","option_id":"A","confidence":0.86,"reason":"The user said they have had this experience before.","detected_language":"zh","spoken_choice":"freeform"}

Unclear example:
{"status":"unclear","option_id":null,"confidence":0.2,"reason":"The answer is too ambiguous to map to an option.","detected_language":"unknown","spoken_choice":"unclear"}
"""


_REPAIR_SYSTEM_PROMPT = """Convert malformed rubric output into compact valid JSON only.

Rules:
- Do not reinterpret the visitor answer.
- Preserve the original meaning as much as possible.
- Return one JSON object only.
- Do not use Markdown, code fences, or explanations.
- Use status accepted or unclear.
- Use option_id as a string or null.
- Use confidence as a number between 0 and 1.
- Use reason as a string.
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
            "C": {
                "id": "C",
                "text_en": "Other. Say anything.",
                "text_zh": "其他。可以随便说。",
            },
        },
        "scoring_options": options,
        "visitor_transcript": transcript,
        "stt_detected_language": detected_language,
    }
    return json.dumps(payload, ensure_ascii=False)


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
                "status": "accepted or unclear",
                "option_id": "A, B, or null",
                "confidence": "number between 0 and 1",
                "reason": "string",
                "detected_language": "zh, en, mixed, or unknown",
                "spoken_choice": "A, B, C, freeform, or unclear",
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
    option_id = _normalize_option_id(payload.get("option_id"))
    status = str(payload.get("status") or "").strip().lower()
    if status not in {"accepted", "unclear"}:
        status = "accepted" if option_id else "unclear"

    if option_id is not None and option_id not in valid_options:
        option_id = None
        status = "unclear"
    if status == "accepted" and option_id is None:
        status = "unclear"
    if status == "unclear" or confidence < 0.65:
        option_id = None
        status = "unclear"

    reason = str(payload.get("reason") or "").strip()
    reason_zh = str(payload.get("reason_zh") or reason or "没太听清，请再说一遍。")
    reason_en = str(
        payload.get("reason_en")
        or reason
        or "The answer is unclear; please try again."
    )
    normalized = dict(payload)
    normalized["status"] = status
    normalized["option_id"] = option_id
    normalized["confidence"] = confidence
    if reason and "reason" not in normalized:
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
    )


def _normalize_option_id(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized or normalized.lower() in {"null", "none"}:
        return None
    return normalized.upper()


def _coerce_confidence(value: Any) -> float:
    try:
        return _clamp(float(value), 0.0, 1.0)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
