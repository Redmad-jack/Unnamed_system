from __future__ import annotations

from conscious_entity.core.config_loader import load_config
from conscious_entity.shopkeeper.models import Language, Scene, ShopAction, StructuredTurn
from conscious_entity.shopkeeper.response_guard import ShopkeeperResponseGuard


def _turn(language=Language.ZH, action=ShopAction.NONE, scene=Scene.MENU_INTRO):
    return StructuredTurn(
        language=language,
        scene=scene,
        reply="",
        action=action,
        next_scene=Scene.ORDER_TAKING,
    )


def test_guard_replaces_chinese_ai_or_customer_service_phrase(config_dir):
    guard = ShopkeeperResponseGuard(load_config("shopkeeper_mode.yaml", config_dir=config_dir))
    reply = guard.apply("您好，请问需要什么帮助？", _turn())
    assert reply == "看看今天这两碗汤吧。"


def test_guard_replaces_english_ai_phrase(config_dir):
    guard = ShopkeeperResponseGuard(load_config("shopkeeper_mode.yaml", config_dir=config_dir))
    reply = guard.apply("As an AI, I can recommend soup.", _turn(Language.EN))
    assert reply == "Take a look. We have two soups today."


def test_guard_limits_long_english_reply(config_dir):
    guard = ShopkeeperResponseGuard(load_config("shopkeeper_mode.yaml", config_dir=config_dir))
    reply = guard.apply(
        "First sentence. Second sentence. Third sentence. Fourth sentence.",
        _turn(Language.EN),
    )
    assert reply == "First sentence. Second sentence. Third sentence."


def test_guard_uses_action_specific_fallback(config_dir):
    guard = ShopkeeperResponseGuard(load_config("shopkeeper_mode.yaml", config_dir=config_dir))
    reply = guard.apply("", _turn(Language.EN, ShopAction.CLARIFY, Scene.FALLBACK))
    assert reply == "I missed that. Which soup would you like?"
