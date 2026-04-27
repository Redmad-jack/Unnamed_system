from __future__ import annotations

import shutil

import pytest

from conscious_entity.core.config_loader import load_all_configs, load_config


def test_load_all_configs_includes_shopkeeper_mode(config_dir):
    configs = load_all_configs(config_dir)
    assert "shopkeeper_mode" in configs
    assert configs["shopkeeper_mode"]["menu"]["items"]["ai_miao"]["display"]["zh"] == "艾苗汤"


def test_shopkeeper_mode_requires_expected_top_level_keys(config_dir):
    cfg = load_config("shopkeeper_mode.yaml", config_dir=config_dir)
    for key in ("version", "menu", "language", "scenes", "visual_tags", "style"):
        assert key in cfg


def test_load_all_configs_requires_shopkeeper_mode(tmp_path, config_dir):
    for path in config_dir.glob("*.yaml"):
        if path.name == "shopkeeper_mode.yaml":
            continue
        shutil.copy(path, tmp_path / path.name)

    with pytest.raises(FileNotFoundError, match="shopkeeper_mode.yaml"):
        load_all_configs(tmp_path)
