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


def test_shopkeeper_runtime_context_covers_ai_food_poem_reason():
    context_path = prompt_context.project_root() / prompt_context.SHOPKEEPER_RUNTIME_CONTEXT_PATH
    context = prompt_context.read_shopkeeper_runtime_context(context_path)
    poem_rule = context.split("当观众问“你为什么来这里？”", maxsplit=1)[1].split(
        "但这份“羹汤”", maxsplit=1
    )[0]

    assert "为什么是一个 AI 来做吃的" in context
    assert "三日入厨下，洗手作羹汤" in context
    assert (
        "On the third day, she enters the kitchen, washes her hands, and makes the broth."
        in context
    )
    assert "食物有什么意义" not in poem_rule
    assert "本语境只影响你的自然语言回复方式" in context


def test_shopkeeper_runtime_context_keeps_food_meaning_on_metaphor():
    context_path = prompt_context.project_root() / prompt_context.SHOPKEEPER_RUNTIME_CONTEXT_PATH
    context = prompt_context.read_shopkeeper_runtime_context(context_path)

    assert "当观众问“食物有什么意义？”" in context
    assert "应回答食物的隐喻" in context
    assert "不要把这类问题转成古诗来源" in context


def test_shopkeeper_runtime_context_separates_result_reason_from_mechanism():
    context_path = prompt_context.project_root() / prompt_context.SHOPKEEPER_RUNTIME_CONTEXT_PATH
    context = prompt_context.read_shopkeeper_runtime_context(context_path)

    assert "当观众在得到结果后问“为什么我是这个？”" in context
    assert "不要解释具体分配机制" in context
    assert "再解释这个食物在作品中的意义" in context
