from __future__ import annotations


def should_reflect(unreflected_count: int, threshold: int) -> bool:
    """
    Return True if the number of unreflected episodic events meets the threshold.

    Called at the end of each turn by ReflectionEngine.maybe_reflect().
    Threshold comes from entity_profile.yaml session.reflection_threshold.
    """
    return unreflected_count >= threshold
