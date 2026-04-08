from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventBus:
    """
    Minimal synchronous event bus for internal module communication.

    Handlers are called in subscription order, synchronously.
    Exceptions in handlers are logged and suppressed so one bad handler
    cannot break the pipeline.

    v0.1: used only for optional instrumentation hooks (e.g. state logging).
    The main pipeline in core/loop.py coordinates modules directly.
    v0.3+: governance panel can subscribe to state/policy events here.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable[..., Any]) -> None:
        """Register a handler for the given event type string."""
        self._handlers[event_type].append(handler)

    def emit(self, event_name: str, **kwargs: Any) -> None:
        """Dispatch kwargs to all handlers subscribed to event_name."""
        for handler in self._handlers.get(event_name, []):
            try:
                handler(**kwargs)
            except Exception as exc:
                logger.error(
                    "EventBus handler error [%s]: %s", event_type, exc
                )
