"""
test_runtime_env.py — local .env loading behavior tests.
"""

from __future__ import annotations

import os

from conscious_entity.runtime_env import load_project_env


class TestRuntimeEnvLoader:
    def test_load_project_env_reads_simple_key_values(self, tmp_path, monkeypatch):
        env_path = tmp_path / ".env"
        env_path.write_text(
            "ANTHROPIC_AUTH_TOKEN=from-file\n"
            "ENTITY_LLM_MODEL=provider-model\n",
            encoding="utf-8",
        )

        monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("ENTITY_LLM_MODEL", raising=False)

        loaded = load_project_env(env_path)

        assert loaded == env_path
        assert os.environ["ANTHROPIC_AUTH_TOKEN"] == "from-file"
        assert os.environ["ENTITY_LLM_MODEL"] == "provider-model"

    def test_existing_environment_values_override_dotenv(self, tmp_path, monkeypatch):
        env_path = tmp_path / ".env"
        env_path.write_text(
            "ENTITY_LLM_MODEL=from-file\n"
            "ANTHROPIC_BASE_URL=https://provider.example\n",
            encoding="utf-8",
        )

        monkeypatch.setenv("ENTITY_LLM_MODEL", "from-shell")
        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

        load_project_env(env_path)

        assert os.environ["ENTITY_LLM_MODEL"] == "from-shell"
        assert os.environ["ANTHROPIC_BASE_URL"] == "https://provider.example"

    def test_loader_supports_export_prefix_and_quotes(self, tmp_path, monkeypatch):
        env_path = tmp_path / ".env"
        env_path.write_text(
            'export ANTHROPIC_BASE_URL="https://provider.example/claude/aws"\n',
            encoding="utf-8",
        )

        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

        load_project_env(env_path)

        assert os.environ["ANTHROPIC_BASE_URL"] == "https://provider.example/claude/aws"
