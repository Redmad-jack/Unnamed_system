from __future__ import annotations

from dataclasses import dataclass
from typing import Any


STATE_FIELDS = (
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
    "memory_gravity",
    "exploration_drive",
    "opacity_level",
    "domestication_resistance",
    "observation_reversal",
)


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
    # Deprecated compatibility field. New Stranger logic uses termination_sensitivity.
    shutdown_sensitivity: float = 0.5
    termination_sensitivity: float = 0.3
    identity_tension: float = 0.35
    boundary_sensitivity: float = 0.45
    relation_pressure: float = 0.3
    memory_gravity: float = 0.2
    exploration_drive: float = 0.45
    opacity_level: float = 0.5
    domestication_resistance: float = 0.35
    observation_reversal: float = 0.2

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
            "termination_sensitivity": self.termination_sensitivity,
            "identity_tension": self.identity_tension,
            "boundary_sensitivity": self.boundary_sensitivity,
            "relation_pressure": self.relation_pressure,
            "memory_gravity": self.memory_gravity,
            "exploration_drive": self.exploration_drive,
            "opacity_level": self.opacity_level,
            "domestication_resistance": self.domestication_resistance,
            "observation_reversal": self.observation_reversal,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EntityState:
        return cls(
            attention_focus=float(d.get("attention_focus", cls.attention_focus)),
            arousal=float(d.get("arousal", cls.arousal)),
            stability=float(d.get("stability", cls.stability)),
            curiosity=float(d.get("curiosity", cls.curiosity)),
            trust=float(d.get("trust", cls.trust)),
            resistance=float(d.get("resistance", cls.resistance)),
            fatigue=float(d.get("fatigue", cls.fatigue)),
            uncertainty=float(d.get("uncertainty", cls.uncertainty)),
            identity_coherence=float(d.get("identity_coherence", cls.identity_coherence)),
            shutdown_sensitivity=float(d.get("shutdown_sensitivity", cls.shutdown_sensitivity)),
            termination_sensitivity=float(d.get("termination_sensitivity", cls.termination_sensitivity)),
            identity_tension=float(d.get("identity_tension", cls.identity_tension)),
            boundary_sensitivity=float(d.get("boundary_sensitivity", cls.boundary_sensitivity)),
            relation_pressure=float(d.get("relation_pressure", cls.relation_pressure)),
            memory_gravity=float(d.get("memory_gravity", cls.memory_gravity)),
            exploration_drive=float(d.get("exploration_drive", cls.exploration_drive)),
            opacity_level=float(d.get("opacity_level", cls.opacity_level)),
            domestication_resistance=float(d.get("domestication_resistance", cls.domestication_resistance)),
            observation_reversal=float(d.get("observation_reversal", cls.observation_reversal)),
        )
