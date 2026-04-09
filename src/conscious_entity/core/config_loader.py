"""
config_loader.py — typed YAML loading with startup validation.

Loads and validates configuration files from the config directory.
Raises descriptive errors on startup if configs are malformed.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

# Required top-level keys per config file.
_REQUIRED_KEYS: dict[str, list[str]] = {
    "state_rules.yaml": ["version", "decay", "events"],
    "policy_rules.yaml": ["version", "rules"],
    "constitution.yaml": ["version", "forbidden_claims", "expression_filters"],
    "expression_mappings.yaml": ["version", "tone_rules", "delay_rules", "visual_mode_rules"],
    "entity_profile.yaml": ["version", "identity", "initial_state", "session"],
}


def _default_config_dir() -> Path:
    return Path(os.getenv("ENTITY_CONFIG_DIR", "config"))


def load_config(filename: str, config_dir: Path | None = None) -> dict[str, Any]:
    """
    Load a YAML config file and validate its required top-level keys.

    Args:
        filename: Config filename relative to the config directory (e.g. 'state_rules.yaml').
        config_dir: Override the default config directory. Useful in tests.

    Returns:
        Parsed config as a dict.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If required top-level keys are missing.
        yaml.YAMLError: If the file is not valid YAML.
    """
    base = config_dir or _default_config_dir()
    path = base / filename

    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            f"Ensure '{filename}' exists in '{base}'."
        )

    with open(path, encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise yaml.YAMLError(
                f"YAML parse error in '{path}':\n{exc}"
            ) from exc

    if data is None:
        raise ValueError(f"Config file is empty: {path}")

    required = _REQUIRED_KEYS.get(filename, [])
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(
            f"Config file '{path}' is missing required keys: {missing}"
        )

    return data


def load_all_configs(config_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """
    Load and validate all five config files at once.

    Returns:
        Dict keyed by filename (without extension), e.g. {'state_rules': {...}, ...}

    Raises:
        On first validation error encountered.
    """
    base = config_dir or _default_config_dir()
    configs = {}
    for filename in _REQUIRED_KEYS:
        key = filename.replace(".yaml", "")
        configs[key] = load_config(filename, config_dir=base)
    return configs
