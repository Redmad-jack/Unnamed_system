"""
test_cli.py — CLI startup validation tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conscious_entity.interfaces import cli


class TestCliStartupValidation:
    def test_cli_exits_with_clear_message_when_llm_config_is_missing(
        self,
        tmp_path: Path,
        monkeypatch,
        capsys,
    ):
        for key in (
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_BASE_URL",
            "ENTITY_LLM_MODEL",
            "ENTITY_LLM_MESSAGES_ENDPOINT",
        ):
            monkeypatch.delenv(key, raising=False)

        monkeypatch.setattr(cli, "load_project_env", lambda: None)
        monkeypatch.setattr(cli, "_find_db_path", lambda: tmp_path / "memory.db")
        monkeypatch.setattr(sys, "argv", ["conscious-entity"])

        with pytest.raises(SystemExit) as exc:
            cli.main()

        assert exc.value.code == 1
        stderr = capsys.readouterr().err
        assert "LLM configuration error" in stderr
        assert "ANTHROPIC_API_KEY" in stderr
