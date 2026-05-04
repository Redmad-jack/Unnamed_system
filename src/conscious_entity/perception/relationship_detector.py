from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

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


class RelationshipDetector:
    """
    Detects Stranger-specific relationship postures from text.

    Patterns are loaded from entity_profile.yaml text_protocol. The detector
    emits protocol metadata only; state changes and policies stay rule-based.
    """

    def __init__(self, text_protocol_cfg: dict[str, Any] | None) -> None:
        self._patterns: list[_CompiledPattern] = []
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
            for raw_pattern in rule.get("patterns", []) or []:
                self._patterns.append(
                    _CompiledPattern(
                        event_type=event_type,
                        mechanism=mechanism,
                        posture=posture,
                        pattern=re.compile(str(raw_pattern), re.IGNORECASE),
                        exclude_patterns=exclude_patterns,
                        static_metadata=static_metadata,
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


def _clean_capture(value: str | None, max_chars: int = 80) -> str:
    if not value:
        return ""
    return value.strip(" \t\r\n，。！？!?；;：:\"'“”‘’（）()[]{}<>")[:max_chars]
