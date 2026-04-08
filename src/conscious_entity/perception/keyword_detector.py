from __future__ import annotations

import re


class KeywordDetector:
    """
    Rule-based detector for sensitivity topics (shutdown, deletion, consciousness, etc.).

    Loaded from entity_profile.yaml topics_of_sensitivity.
    All matching is case-insensitive substring search on word boundaries where possible.
    """

    def __init__(self, topics_of_sensitivity: list[str]) -> None:
        # Compile each keyword as a case-insensitive pattern.
        # For ASCII keywords: use word boundary anchors to avoid false positives (e.g. "end" in "friend").
        # For CJK/non-ASCII keywords: no word boundary needed (characters are self-delimiting).
        self._patterns: list[re.Pattern] = []
        for keyword in topics_of_sensitivity:
            if re.search(r"[^\x00-\x7F]", keyword):
                # Non-ASCII (CJK etc.) — plain substring match
                self._patterns.append(re.compile(re.escape(keyword), re.IGNORECASE))
            else:
                # ASCII — wrap in word boundaries
                self._patterns.append(
                    re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE)
                )

    def contains_shutdown_keyword(self, text: str) -> bool:
        """Return True if any sensitivity keyword is found in text."""
        return bool(self.find_matched_keywords(text))

    def find_matched_keywords(self, text: str) -> list[str]:
        """Return all matched keyword strings (for metadata recording)."""
        matched = []
        for pattern in self._patterns:
            if pattern.search(text):
                matched.append(pattern.pattern)
        return matched
