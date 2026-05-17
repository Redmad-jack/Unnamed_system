from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from conscious_entity.runtime_env import project_root


SHOPKEEPER_RUNTIME_CONTEXT_PATH = Path("backend/prompts/shopkeeper_runtime_context.md")


@lru_cache(maxsize=1)
def shopkeeper_runtime_context() -> str:
    """Load the shopkeeper runtime context once per process."""
    return read_shopkeeper_runtime_context(project_root() / SHOPKEEPER_RUNTIME_CONTEXT_PATH)


def read_shopkeeper_runtime_context(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
