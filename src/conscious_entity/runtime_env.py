"""
runtime_env.py — lightweight project .env loading for local development.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)


def project_root() -> Path:
    """Return the repository root for runtime assets such as .env and data/."""
    return _PROJECT_ROOT


def default_env_path() -> Path:
    """Return the default .env path at the project root."""
    return _PROJECT_ROOT / ".env"


def load_project_env(env_path: Path | None = None, *, override: bool = False) -> Path | None:
    """
    Load KEY=VALUE pairs from the project's .env file.

    Existing environment variables win by default so CI and shell exports can
    override local development defaults.
    """
    path = env_path or default_env_path()
    if not path.exists():
        return None

    seen_keys: set[str] = set()
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue

        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        if key in seen_keys:
            logger.warning(
                "Duplicate key %s in %s at line %s; the first value remains active unless override=True.",
                key,
                path,
                line_no,
            )
        else:
            seen_keys.add(key)

        if override or key not in os.environ:
            os.environ[key] = _parse_env_value(raw_value.strip())

    return path


def _parse_env_value(raw_value: str) -> str:
    if not raw_value:
        return ""

    if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in {"'", '"'}:
        return raw_value[1:-1]

    inline_comment = raw_value.find(" #")
    if inline_comment != -1:
        return raw_value[:inline_comment].rstrip()

    return raw_value
