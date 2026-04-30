from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def default_config_dir(project_root: Path) -> Path:
    return project_root / "config" / "have_some_ai"


def load_have_some_ai_config(config_dir: Path) -> dict[str, Any]:
    """Load the Have Some "Ai" question bank and scoring rules."""
    questions_path = config_dir / "questions.yaml"
    scoring_path = config_dir / "scoring.yaml"

    if not questions_path.exists():
        raise FileNotFoundError(f"Missing question bank: {questions_path}")
    if not scoring_path.exists():
        raise FileNotFoundError(f"Missing scoring config: {scoring_path}")

    return {
        "questions": _load_yaml(questions_path),
        "scoring": _load_yaml(scoring_path),
    }


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping at {path}")
    return data
