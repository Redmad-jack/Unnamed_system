from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EntityState:
    attention_focus: float = 0.5
    arousal: float = 0.3
    stability: float = 0.7
    curiosity: float = 0.5
    trust: float = 0.5
    resistance: float = 0.2
    fatigue: float = 0.0
    uncertainty: float = 0.3
    identity_coherence: float = 0.8
    shutdown_sensitivity: float = 0.5

    def clamp_all(self) -> EntityState:
        """Return a new EntityState with all fields clamped to [0.0, 1.0]."""
        return EntityState(
            **{k: max(0.0, min(1.0, v)) for k, v in self.to_dict().items()}
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "attention_focus": self.attention_focus,
            "arousal": self.arousal,
            "stability": self.stability,
            "curiosity": self.curiosity,
            "trust": self.trust,
            "resistance": self.resistance,
            "fatigue": self.fatigue,
            "uncertainty": self.uncertainty,
            "identity_coherence": self.identity_coherence,
            "shutdown_sensitivity": self.shutdown_sensitivity,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EntityState:
        return cls(
            attention_focus=float(d["attention_focus"]),
            arousal=float(d["arousal"]),
            stability=float(d["stability"]),
            curiosity=float(d["curiosity"]),
            trust=float(d["trust"]),
            resistance=float(d["resistance"]),
            fatigue=float(d["fatigue"]),
            uncertainty=float(d["uncertainty"]),
            identity_coherence=float(d["identity_coherence"]),
            shutdown_sensitivity=float(d["shutdown_sensitivity"]),
        )
