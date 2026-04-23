from __future__ import annotations


MANAGER_TG_URL = "https://t.me/adkcosmetics"
MANAGER_BUTTON_TEXT = "Написать менеджеру"
INSTRUCTION_SEARCH_BUTTON_TEXT = "Поиск инструкции"


def consent_keyboard(privacy_policy_url: str) -> dict:
    return {
        "inline_keyboard": [
            [{"text": "Принимаю", "callback_data": "consent_accept"}],
            [{"text": "Политика конфиденциальности", "url": privacy_policy_url}],
        ]
    }


def check_subscription_keyboard() -> dict:
    return {"inline_keyboard": [[{"text": "Проверить подписку", "callback_data": "check_subscription"}]]}


def retry_subscription_keyboard(channel_url: str) -> dict:
    return {
        "inline_keyboard": [
            [{"text": "Подписаться", "url": channel_url}],
            [{"text": "Проверить снова", "callback_data": "check_subscription"}],
        ]
    }


def manager_link_keyboard() -> dict:
    return {"inline_keyboard": [[{"text": MANAGER_BUTTON_TEXT, "url": MANAGER_TG_URL}]]}


def manager_reply_keyboard() -> dict:
    return {
        "keyboard": [[{"text": INSTRUCTION_SEARCH_BUTTON_TEXT}, {"text": MANAGER_BUTTON_TEXT}]],
        "resize_keyboard": True,
        "is_persistent": True,
        "one_time_keyboard": False,
    }
