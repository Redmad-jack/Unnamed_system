from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from conscious_entity.perception.event_types import EventType


@dataclass(frozen=True)
class RelationshipSignal:
    event_type: EventType
    metadata: dict[str, Any]


@dataclass(frozen=True)
class _CompiledPattern:
    event_type: EventType
    mechanism: str
    posture: str
    pattern: re.Pattern
    exclude_patterns: list[re.Pattern]
    static_metadata: dict[str, Any]


@dataclass(frozen=True)
class _FollowupRule:
    event_type: EventType
    mechanism: str
    posture: str
    max_chars: int
    fragment_patterns: list[re.Pattern]
    exit_patterns: list[re.Pattern]
    static_metadata: dict[str, Any]


class RelationshipDetector:
    """
    Detects Stranger-specific relationship postures from text.

    Patterns are loaded from entity_profile.yaml text_protocol. The detector
    emits protocol metadata only; state changes and policies stay rule-based.
    """

    def __init__(self, text_protocol_cfg: dict[str, Any] | None) -> None:
        self._patterns: list[_CompiledPattern] = []
        self._followup_rules: list[_FollowupRule] = []
        if not text_protocol_cfg:
            return

        for event_name, rule in text_protocol_cfg.items():
            if not isinstance(rule, dict):
                continue
            try:
                event_type = EventType(event_name)
            except ValueError:
                continue

            mechanism = str(rule.get("mechanism", event_name))
            posture = str(rule.get("posture", event_name))
            static_metadata = dict(rule.get("metadata", {}) or {})
            exclude_patterns = [
                re.compile(str(raw_pattern), re.IGNORECASE)
                for raw_pattern in rule.get("exclude_patterns", []) or []
            ]
            followup = rule.get("followup", {}) or {}
            if isinstance(followup, dict) and followup.get("enabled", False):
                fragment_patterns = [
                    re.compile(str(raw_pattern), re.IGNORECASE)
                    for raw_pattern in followup.get("fragment_patterns", []) or []
                ]
                exit_patterns = [
                    re.compile(str(raw_pattern), re.IGNORECASE)
                    for raw_pattern in followup.get("exit_patterns", []) or []
                ]
                self._followup_rules.append(
                    _FollowupRule(
                        event_type=event_type,
                        mechanism=mechanism,
                        posture=str(followup.get("posture", f"{posture}_followup")),
                        max_chars=int(followup.get("max_chars", 24)),
                        fragment_patterns=fragment_patterns,
                        exit_patterns=exit_patterns,
                        static_metadata=static_metadata,
                    )
                )
            for raw_pattern in rule.get("patterns", []) or []:
                if isinstance(raw_pattern, dict):
                    pattern_text = raw_pattern.get("pattern")
                    if not pattern_text:
                        continue
                    pattern_metadata = dict(raw_pattern.get("metadata", {}) or {})
                else:
                    pattern_text = raw_pattern
                    pattern_metadata = {}
                compiled_metadata = dict(static_metadata)
                compiled_metadata.update(pattern_metadata)
                self._patterns.append(
                    _CompiledPattern(
                        event_type=event_type,
                        mechanism=mechanism,
                        posture=posture,
                        pattern=re.compile(str(pattern_text), re.IGNORECASE),
                        exclude_patterns=exclude_patterns,
                        static_metadata=compiled_metadata,
                    )
                )

    def detect(self, text: str) -> list[RelationshipSignal]:
        """Return at most one signal per EventType, in YAML rule order."""
        signals: list[RelationshipSignal] = []
        emitted: set[EventType] = set()

        for item in self._patterns:
            if item.event_type in emitted:
                continue

            match = item.pattern.search(text)
            if match is None:
                continue
            if any(pattern.search(text) for pattern in item.exclude_patterns):
                continue

            metadata: dict[str, Any] = {
                "protocol": "stranger_text",
                "mechanism": item.mechanism,
                "posture": item.posture,
                "matched_phrase": _clean_capture(match.group(0)),
            }
            metadata.update(item.static_metadata)
            for key, value in match.groupdict().items():
                cleaned = _clean_capture(value)
                if cleaned:
                    metadata[key] = cleaned

            signals.append(RelationshipSignal(item.event_type, metadata))
            emitted.add(item.event_type)

        return signals

    def detect_followup(self, text: str, recent_entries: Iterable[Any]) -> list[RelationshipSignal]:
        """
        Detect short contextual continuations of a previous relationship posture.

        This catches cases such as a visitor first making a service demand, then
        sending only a field name or topic fragment on the next turn.
        """
        signals: list[RelationshipSignal] = []
        emitted: set[EventType] = set()

        for rule in self._followup_rules:
            if rule.event_type in emitted:
                continue
            if not _is_followup_fragment(text, rule):
                continue

            prior = _last_user_entry(recent_entries)
            if prior is None:
                continue
            prior_event_type = getattr(prior, "event_type", None)
            prior_matches = _entry_matches_event(self.detect(prior.content), rule.event_type)
            if prior_event_type != rule.event_type and not prior_matches:
                continue

            metadata: dict[str, Any] = {
                "protocol": "stranger_text",
                "mechanism": rule.mechanism,
                "posture": rule.posture,
                "matched_phrase": _clean_capture(text),
                "contextual_followup": True,
                "continuation_of": rule.event_type.value,
                "prior_request": _clean_capture(prior.content),
            }
            metadata.update(rule.static_metadata)

            signals.append(RelationshipSignal(rule.event_type, metadata))
            emitted.add(rule.event_type)

        return signals


def _clean_capture(value: str | None, max_chars: int = 80) -> str:
    if not value:
        return ""
    return value.strip(" \t\r\n，。！？!?；;：:\"'“”‘’（）()[]{}<>")[:max_chars]


def _is_followup_fragment(text: str, rule: _FollowupRule) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if any(pattern.search(stripped) for pattern in rule.exit_patterns):
        return False
    if len(stripped) > rule.max_chars:
        return False
    return not rule.fragment_patterns or any(
        pattern.search(stripped) for pattern in rule.fragment_patterns
    )


def _last_user_entry(entries: Iterable[Any]) -> Any | None:
    for entry in reversed(list(entries)):
        if getattr(entry, "role", None) == "user":
            return entry
    return None


def _entry_matches_event(signals: list[RelationshipSignal], event_type: EventType) -> bool:
    return any(signal.event_type == event_type for signal in signals)
