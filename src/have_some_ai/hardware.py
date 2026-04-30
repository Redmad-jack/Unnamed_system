from __future__ import annotations

from typing import Any, Protocol

from have_some_ai.models import Assignment


class HardwareAdapter(Protocol):
    """Future boundary for printers, lights, sensors, and kitchen signals."""

    def on_assignment(self, assignment: Assignment, context: dict[str, Any]) -> None:
        ...


class NullHardwareAdapter:
    """Default adapter used before physical devices are connected."""

    def on_assignment(self, assignment: Assignment, context: dict[str, Any]) -> None:
        return None
