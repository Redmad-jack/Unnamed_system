from __future__ import annotations

from conscious_entity.harness import (
    HarnessLayer,
    HarnessTraceRecorder,
    HarnessTraceStore,
    get_harness_trace_store,
)
from conscious_entity.memory.short_term import ShortTermMemory
from conscious_entity.policy.policy_selector import PolicySelector
from conscious_entity.policy.policy_types import PolicyAction
from conscious_entity.state.state_core import EntityState


def test_trace_recorder_records_layer_public_fields():
    recorder = HarnessTraceRecorder(
        session_id="session-1",
        source="dialog",
        metadata={"input_mode": "text"},
    )

    recorder.record(
        HarnessLayer.INPUT,
        status="tagged",
        rule_ids=["input:text"],
        decision="accepted",
        summary="Input parsed.",
        metadata={"event_types": ["user_spoke"]},
    )
    trace = recorder.finish(success=True)

    payload = trace.to_public_dict()
    assert payload["session_id"] == "session-1"
    assert payload["metadata"]["input_mode"] == "text"
    assert payload["layers"][0]["layer"] == "input"
    assert payload["layers"][0]["rule_ids"] == ["input:text"]
    assert payload["summary"]["layers"]["input"]["status"] == "tagged"


def test_trace_store_returns_recent_records_in_order():
    store = HarnessTraceStore(max_records=2)
    for index in range(3):
        recorder = HarnessTraceRecorder(
            session_id=f"session-{index}",
            source="dialog",
        )
        recorder.record(HarnessLayer.POLICY, status="selected", summary="ok")
        store.record(recorder.finish(success=True))

    recent = store.recent(limit=10)

    assert len(recent) == 2
    assert [trace.session_id for trace in recent] == ["session-1", "session-2"]
    assert store.status()["recent_count"] == 2


def test_global_trace_store_can_be_cleared():
    store = get_harness_trace_store()
    store.clear()
    assert store.latest() is None
    assert store.status()["latest"] is None


def test_policy_selection_and_constitution_veto_enter_trace():
    class BlockingOnceConstitution:
        def __init__(self):
            self.calls = 0

        def check(self, action, state, events):
            self.calls += 1
            return False, "mock veto"

    selector = PolicySelector(
        {
            "rules": [
                {
                    "id": "blocked_open",
                    "conditions": {},
                    "action": "respond_openly",
                    "constitution_check": True,
                },
                {
                    "id": "brief_fallback",
                    "conditions": {},
                    "action": "respond_briefly",
                },
            ]
        },
        BlockingOnceConstitution(),
    )
    recorder = HarnessTraceRecorder(session_id="test", source="dialog")

    decision = selector.select(
        EntityState(),
        [],
        ShortTermMemory(max_turns=10),
        harness_recorder=recorder,
    )
    trace = recorder.finish(success=True)

    assert decision.action == PolicyAction.RESPOND_BRIEFLY
    assert [item.status for item in trace.layers] == ["vetoed", "selected"]
    assert trace.layers[0].rule_ids == ["blocked_open"]
    assert trace.layers[1].rule_ids == ["brief_fallback"]
