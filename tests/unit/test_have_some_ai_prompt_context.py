from __future__ import annotations

from have_some_ai import prompt_context


def test_shopkeeper_runtime_context_loader_returns_empty_for_missing_file(tmp_path):
    missing = tmp_path / "missing.md"

    assert prompt_context.read_shopkeeper_runtime_context(missing) == ""


def test_shopkeeper_runtime_context_loader_caches_file_contents(monkeypatch, tmp_path):
    root = tmp_path
    context_path = root / prompt_context.SHOPKEEPER_RUNTIME_CONTEXT_PATH
    context_path.parent.mkdir(parents=True)
    context_path.write_text("first context\n", encoding="utf-8")
    monkeypatch.setattr(prompt_context, "project_root", lambda: root)
    prompt_context.shopkeeper_runtime_context.cache_clear()

    try:
        assert prompt_context.shopkeeper_runtime_context() == "first context"
        context_path.write_text("second context\n", encoding="utf-8")
        assert prompt_context.shopkeeper_runtime_context() == "first context"
        prompt_context.shopkeeper_runtime_context.cache_clear()
        assert prompt_context.shopkeeper_runtime_context() == "second context"
    finally:
        prompt_context.shopkeeper_runtime_context.cache_clear()
