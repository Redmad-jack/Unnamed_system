from __future__ import annotations

from collections import deque

from conscious_entity.memory.models import ShortTermEntry


class ShortTermMemory:
    def __init__(self, max_turns: int = 10) -> None:
        self._buffer: deque[ShortTermEntry] = deque(maxlen=max_turns)

    def add(self, entry: ShortTermEntry) -> None:
        self._buffer.append(entry)

    def get_recent(self, n: int = 5) -> list[ShortTermEntry]:
        """Return the most recent n entries in chronological order (oldest first)."""
        entries = list(self._buffer)
        return entries[-n:] if n < len(entries) else entries

    def count_repetitions(self, text: str) -> int:
        """
        Count how many recent user turns semantically resemble the given text.
        v0.1: word-overlap heuristic — overlap / min(len_a, len_b) >= 0.5.
        """
        words = set(text.lower().split())
        if not words:
            return 0
        count = 0
        for entry in self._buffer:
            if entry.role != "user":
                continue
            entry_words = set(entry.content.lower().split())
            if not entry_words:
                continue
            overlap = len(words & entry_words) / min(len(words), len(entry_words))
            if overlap >= 0.5:
                count += 1
        return count
