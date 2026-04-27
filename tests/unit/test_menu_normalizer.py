from __future__ import annotations

import pytest

from conscious_entity.core.config_loader import load_config
from conscious_entity.shopkeeper.menu import MenuCatalog, normalize_soup
from conscious_entity.shopkeeper.models import Language, SoupId


@pytest.fixture
def catalog(config_dir):
    cfg = load_config("shopkeeper_mode.yaml", config_dir=config_dir)
    return MenuCatalog.from_config(cfg)


def test_normalizes_chinese_ai_miao_name(catalog):
    match = catalog.normalize_soup("来一碗艾苗汤")
    assert match is not None
    assert match.soup_id == SoupId.AI_MIAO
    assert match.display_name == "艾苗汤"
    assert match.language == Language.ZH


def test_normalizes_english_ai_miao_name(catalog):
    match = catalog.normalize_soup("Can I get an Ai Sprout Soup?")
    assert match is not None
    assert match.soup_id == SoupId.AI_MIAO
    assert match.display_name == "Ai Sprout Soup"
    assert match.language == Language.EN


def test_normalizes_chinese_no_ai_alias(catalog):
    match = catalog.normalize_soup("我想要不加艾的那个普通汤")
    assert match is not None
    assert match.soup_id == SoupId.NO_AI
    assert match.display_name == "没有艾的汤"


def test_normalizes_english_no_ai_aliases_with_priority(catalog):
    for text in ("no ai soup please", "no-ai soup please", "without ai please"):
        match = catalog.normalize_soup(text)
        assert match is not None
        assert match.soup_id == SoupId.NO_AI
        assert match.display_name == "General Soup"


def test_bare_ai_does_not_match_ai_miao(catalog):
    assert catalog.normalize_soup("ai") is None


def test_module_level_normalize_soup_delegates_to_catalog(catalog):
    match = normalize_soup("plain soup", catalog)
    assert match is not None
    assert match.soup_id == SoupId.NO_AI


def test_rejects_bare_ai_alias_for_ai_miao(config_dir):
    cfg = load_config("shopkeeper_mode.yaml", config_dir=config_dir)
    cfg["menu"]["items"]["ai_miao"]["aliases"]["en"].append("ai")

    with pytest.raises(ValueError, match="Bare 'ai'"):
        MenuCatalog.from_config(cfg)
