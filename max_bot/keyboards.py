from __future__ import annotations

from typing import Any


MANAGER_MAX_URL = "https://max.ru/u/f9LHodD0cOIJgI1mtlCcMCXlLn0ey0DuDWwbXaDEfcKeWxl5I6wL7-Uzc5Y"


def _inline(buttons: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]


def consent_keyboard(privacy_policy_url: str) -> list[dict[str, Any]]:
    return _inline(
        [
            [{"type": "callback", "text": "Принимаю", "payload": "consent_accept"}],
            [{"type": "link", "text": "Политика конфиденциальности", "url": privacy_policy_url}],
        ]
    )


def check_subscription_keyboard() -> list[dict[str, Any]]:
    return _inline([[{"type": "callback", "text": "Проверить подписку", "payload": "check_subscription"}]])


def retry_subscription_keyboard(channel_url: str) -> list[dict[str, Any]]:
    return _inline(
        [
            [{"type": "link", "text": "Подписаться", "url": channel_url}],
            [{"type": "callback", "text": "Проверить снова", "payload": "check_subscription"}],
        ]
    )


def manager_keyboard() -> list[dict[str, Any]]:
    return _inline(
        [
            [{"type": "callback", "text": "Поиск инструкции", "payload": "instruction_search_open"}],
            [{"type": "link", "text": "Написать менеджеру", "url": MANAGER_MAX_URL}],
        ]
    )
