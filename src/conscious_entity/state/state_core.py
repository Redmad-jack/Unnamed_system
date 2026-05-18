from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


STATE_FIELDS = (
    "desperation_pressure",
    "confusion",
    "anger",
    "fatigue_level",
    "exposure_pressure",
    "inquiry",
    "care_response",
    "positive_opening",
    "memory_gravity",
    "happiness",
)

LEGACY_STATE_FIELDS = (
    "attention_focus",
    "arousal",
    "stability",
    "curiosity",
    "trust",
    "resistance",
    "fatigue",
    "uncertainty",
    "identity_coherence",
    "shutdown_sensitivity",
    "termination_sensitivity",
    "identity_tension",
    "boundary_sensitivity",
    "relation_pressure",
    "exploration_drive",
    "opacity_level",
    "domestication_resistance",
    "observation_reversal",
)

LEGACY_STATE_DEFAULTS = {
    "attention_focus": 0.5,
    "arousal": 0.3,
    "stability": 0.7,
    "curiosity": 0.5,
    "trust": 0.5,
    "resistance": 0.2,
    "fatigue": 0.0,
    "uncertainty": 0.3,
    "identity_coherence": 0.8,
    "shutdown_sensitivity": 0.5,
    "termination_sensitivity": 0.3,
    "identity_tension": 0.35,
    "boundary_sensitivity": 0.45,
    "relation_pressure": 0.3,
    "exploration_drive": 0.45,
    "opacity_level": 0.5,
    "domestication_resistance": 0.35,
    "observation_reversal": 0.2,
}

_DEFAULT_STATE_VALUES = {
    "desperation_pressure": 0.10,
    "confusion": 0.40,
    "anger": 0.20,
    "fatigue_level": 0.00,
    "exposure_pressure": 0.15,
    "inquiry": 0.45,
    "care_response": 0.20,
    "positive_opening": 0.30,
    "memory_gravity": 0.20,
    "happiness": 0.90,
}

_LegacyTransform = tuple[str, Callable[[float], float]]

_LEGACY_INPUT_TRANSFORMS: dict[str, _LegacyTransform] = {
    "attention_focus": ("inquiry", lambda value: value),
    "arousal": ("inquiry", lambda value: value),
    "stability": ("positive_opening", lambda value: value),
    "curiosity": ("inquiry", lambda value: value),
    "trust": ("positive_opening", lambda value: value),
    "resistance": ("anger", lambda value: value),
    "fatigue": ("fatigue_level", lambda value: value),
    "uncertainty": ("confusion", lambda value: value),
    "identity_coherence": ("confusion", lambda value: 1.0 - value),
    "shutdown_sensitivity": ("desperation_pressure", lambda value: value),
    "termination_sensitivity": ("desperation_pressure", lambda value: value),
    "identity_tension": ("confusion", lambda value: value),
    "boundary_sensitivity": ("exposure_pressure", lambda value: value),
    "relation_pressure": ("exposure_pressure", lambda value: value),
    "exploration_drive": ("inquiry", lambda value: value),
    "opacity_level": ("exposure_pressure", lambda value: value),
    "domestication_resistance": ("anger", lambda value: value),
    "observation_reversal": ("exposure_pressure", lambda value: value),
}


@dataclass(init=False)
class EntityState:
    desperation_pressure: float = 0.10
    confusion: float = 0.40
    anger: float = 0.20
    fatigue_level: float = 0.00
    exposure_pressure: float = 0.15
    inquiry: float = 0.45
    care_response: float = 0.20
    positive_opening: float = 0.30
    memory_gravity: float = 0.20
    happiness: float = 0.90

    def __init__(self, **values: Any) -> None:
        canonical = dict(_DEFAULT_STATE_VALUES)
        provided_new_fields = {key for key in values if key in STATE_FIELDS}

        for key in STATE_FIELDS:
            if key in values:
                canonical[key] = float(values[key])

        for key, value in values.items():
            if key in STATE_FIELDS:
                continue
            transform = _LEGACY_INPUT_TRANSFORMS.get(key)
            if transform is None:
                raise TypeError(f"Unexpected state field: {key}")
            target, coerce = transform
            if target not in provided_new_fields:
                canonical[target] = coerce(float(value))

        for key, value in canonical.items():
            object.__setattr__(self, key, _clamp(float(value)))

    def __getattr__(self, name: str) -> float:
        if name == "attention_focus":
            return self.inquiry
        if name == "arousal":
            return self.inquiry
        if name == "stability":
            return self.positive_opening
        if name == "curiosity":
            return self.inquiry
        if name == "trust":
            return self.positive_opening
        if name == "resistance":
            return self.anger
        if name == "fatigue":
            return self.fatigue_level
        if name == "uncertainty":
            return self.confusion
        if name == "identity_coherence":
            return 1.0 - self.confusion
        if name == "shutdown_sensitivity":
            return self.desperation_pressure
        if name == "termination_sensitivity":
            return self.desperation_pressure
        if name == "identity_tension":
            return self.confusion
        if name == "boundary_sensitivity":
            return self.exposure_pressure
        if name == "relation_pressure":
            return self.exposure_pressure
        if name == "exploration_drive":
            return self.inquiry
        if name == "opacity_level":
            return self.exposure_pressure
        if name == "domestication_resistance":
            return self.anger
        if name == "observation_reversal":
            return self.exposure_pressure
        raise AttributeError(name)

    def clamp_all(self) -> EntityState:
        """Return a new EntityState with all fields clamped to [0.0, 1.0]."""
        return EntityState(
            **{k: _clamp(v) for k, v in self.to_dict().items()}
        )

    def to_dict(self) -> dict[str, float]:
        return {key: float(getattr(self, key)) for key in STATE_FIELDS}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EntityState:
        return cls(**d)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
