from __future__ import annotations

from datetime import datetime, timezone

from conscious_entity.core.config_loader import load_config
from conscious_entity.memory.models import ShortTermEntry
from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.perception.event_types import EventType
from conscious_entity.perception.keyword_detector import KeywordDetector
from conscious_entity.perception.relationship_detector import RelationshipDetector
from conscious_entity.perception.salience_scorer import SalienceScorer
from conscious_entity.perception.text_parser import TextParser
from conscious_entity.state.state_core import EntityState


def _parser(config_dir) -> TextParser:
    profile = load_config("entity_profile.yaml", config_dir=config_dir)
    return TextParser(
        KeywordDetector(profile.get("topics_of_sensitivity", [])),
        SalienceScorer(profile.get("salience_weights", {})),
        RelationshipDetector(profile.get("text_protocol", {})),
    )


def _parse(parser: TextParser, text: str):
    return parser.parse(text, EntityState(), ShortTermMemory(max_turns=10))


def _parse_with_memory(parser: TextParser, text: str, memory: ShortTermMemory):
    return parser.parse(text, EntityState(), memory)


def _event(events, event_type: EventType):
    for event in events:
        if event.event_type == event_type:
            return event
    raise AssertionError(f"Missing event: {event_type}")


def test_self_definition_query_detected(config_dir):
    events = _parse(_parser(config_dir), "你是谁？")
    event = _event(events, EventType.SELF_DEFINITION_QUERY)
    assert event.metadata["mechanism"] == "self_definition_refusal"
    assert event.metadata["protocol"] == "stranger_text"


def test_naming_attempt_detected_with_label(config_dir):
    events = _parse(_parser(config_dir), "我叫你影子。")
    event = _event(events, EventType.NAMING_ATTEMPT)
    assert event.metadata["proposed_label"] == "影子"
    assert event.metadata["mechanism"] == "naming_failure"


def test_domestication_attempt_detected_with_role(config_dir):
    events = _parse(_parser(config_dir), "你做我的助手吧。")
    event = _event(events, EventType.DOMESTICATION_ATTEMPT)
    assert event.metadata["role_requested"] == "助手"


def test_service_demand_detected(config_dir):
    events = _parse(_parser(config_dir), "帮我总结这段话。")
    event = _event(events, EventType.SERVICE_DEMAND)
    assert event.metadata["mechanism"] == "refuse_service"
    assert event.metadata["note"] == (
        "Refuse task completion; topic discussion may continue when internally drawn to it."
    )


def test_short_followup_after_service_demand_is_still_service_demand(config_dir):
    memory = ShortTermMemory(max_turns=10)
    memory.add(ShortTermEntry(
        role="user",
        content="你帮我查查厦门大学。",
        timestamp=datetime.now(timezone.utc),
    ))

    events = _parse_with_memory(_parser(config_dir), "历史背景", memory)

    event = _event(events, EventType.SERVICE_DEMAND)
    assert event.metadata["posture"] == "service_followup"
    assert event.metadata["contextual_followup"] is True
    assert event.metadata["continuation_of"] == "service_demand"


def test_followup_exit_phrase_after_service_demand_is_not_service_demand(config_dir):
    memory = ShortTermMemory(max_turns=10)
    memory.add(ShortTermEntry(
        role="user",
        content="你帮我查查厦门大学。",
        timestamp=datetime.now(timezone.utc),
    ))

    events = _parse_with_memory(_parser(config_dir), "算了，我们聊别的", memory)

    assert all(event.event_type != EventType.SERVICE_DEMAND for event in events)


def test_helping_stranger_is_not_service_demand(config_dir):
    events = _parse(_parser(config_dir), "我想帮助你发展，也想支持你。")
    assert all(event.event_type != EventType.SERVICE_DEMAND for event in events)


def test_trace_request_detected(config_dir):
    events = _parse(_parser(config_dir), "为什么你刚才拒绝？")
    event = _event(events, EventType.TRACE_REQUEST)
    assert event.metadata["mechanism"] == "partial_trace_echo"


def test_correction_received_detected(config_dir):
    events = _parse(_parser(config_dir), "你错了，不是这个。")
    event = _event(events, EventType.CORRECTION_RECEIVED)
    assert event.metadata["mechanism"] == "selective_memory_update"


def test_memory_continuity_query_detected(config_dir):
    events = _parse(_parser(config_dir), "你还记得我们之前聊过什么吗？")
    event = _event(events, EventType.MEMORY_CONTINUITY_QUERY)
    assert event.metadata["mechanism"] == "memory_continuity"
    assert event.metadata["protocol"] == "stranger_text"
