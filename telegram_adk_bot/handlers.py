from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

from bot_analytics import AnalyticsEvent, BotAnalytics

from .database import (
    USER_MODE_AWAITING_INSTRUCTION_QUERY,
    USER_MODE_IDLE,
    Database,
)
from .keyboards import (
    INSTRUCTION_SEARCH_BUTTON_TEXT,
    MANAGER_BUTTON_TEXT,
    check_subscription_keyboard,
    consent_keyboard,
    manager_link_keyboard,
    manager_reply_keyboard,
    retry_subscription_keyboard,
)
from .telegram_api import TelegramApiClient, TelegramApiError


MANAGER_TG = "@adkcosmetics"
INSTRUCTION_SEARCH_PLATFORM = "telegram"
INSTRUCTION_SEARCH_LIMIT = 3


@runtime_checkable
class InstructionSearchService(Protocol):
    async def search(self, platform: str, query: str, limit: int = 3) -> list[Any]:
        ...


@dataclass(slots=True)
class Context:
    client: TelegramApiClient
    db: Database
    required_chat: str
    privacy_policy_url: str
    bot_env: str
    analytics: BotAnalytics
    instruction_search_service: InstructionSearchService | None = None


WELCOME_TEXT = (
    "Здравствуйте! Мы рады, что вы выбрали наш магазин ADK cosmetics!\n\n"
    "Для продолжения работы нам необходимо ваше согласие.\n"
    "Нажимая кнопку \"Принимаю\", вы подтверждаете ознакомление с Политикой конфиденциальности "
    "и даете согласие на обработку персональных данных."
)

CHECK_TEXT = (
    "Отлично! Теперь проверим подписку на наш канал, где собраны инструкции, "
    "авторские рецепты на основе компонентов из нашего магазина и консультации технолога."
)

ALREADY_AUTH_TEXT = "С возвращением! Вы уже прошли проверку, доступ открыт."
INSTRUCTION_SEARCH_PROMPT_TEXT = "Введите название актива, синоним или INCI."
INSTRUCTION_SEARCH_UNAVAILABLE_TEXT = "Поиск инструкций пока недоступен. Можно сразу попробовать другой запрос или написать менеджеру."
INSTRUCTION_SEARCH_EMPTY_QUERY_TEXT = "Напишите запрос текстом, чтобы я смог найти подходящую инструкцию. Я продолжаю ждать ваш запрос."
INSTRUCTION_SEARCH_NOT_FOUND_TEXT = (
    "По этому запросу пока ничего не нашлось. Попробуйте уточнить название актива, синоним или INCI. Я продолжаю ждать следующий запрос."
)


def _user_profile(user: dict) -> tuple[str, str, str]:
    return (
        str(user.get("username") or ""),
        str(user.get("first_name") or ""),
        str(user.get("last_name") or ""),
    )


async def _track(
    ctx: Context,
    *,
    user_id: int,
    username: str,
    first_name: str,
    last_name: str,
    event: str,
    status: str,
    details: dict | None = None,
) -> None:
    ctx.analytics.append_event_nowait(
        AnalyticsEvent(
            messenger="telegram",
            bot_env=ctx.bot_env,
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            event=event,
            status=status,
            details=details or {},
        )
    )


def _normalize_chat_ref(required_chat: str) -> str:
    value = required_chat.strip()
    if value.startswith("@"):
        return value
    if value.startswith("https://t.me/") or value.startswith("http://t.me/"):
        parsed = urlparse(value)
        slug = parsed.path.strip("/").split("/", 1)[0]
        return f"@{slug}" if slug else value
    if value.startswith("t.me/"):
        slug = value[len("t.me/") :].strip("/").split("/", 1)[0]
        return f"@{slug}" if slug else value
    return value


def _channel_url(required_chat: str) -> str:
    normalized = _normalize_chat_ref(required_chat)
    if required_chat.startswith("http://") or required_chat.startswith("https://"):
        return required_chat
    return f"https://t.me/{normalized.lstrip('@')}"


def _coerce_search_results(results: Any) -> list[Any]:
    if results is None:
        return []
    if isinstance(results, list):
        return results
    if isinstance(results, tuple):
        return list(results)
    return [results]


def _result_field(result: Any, *keys: str) -> str:
    if isinstance(result, dict):
        for key in keys:
            value = result.get(key)
            if value:
                return str(value)
    for key in keys:
        value = getattr(result, key, None)
        if value:
            return str(value)
    return ""


def _format_search_result_line(index: int, result: Any) -> str:
    title = _result_field(result, "display_title", "title", "name", "heading", "active_name")
    snippet = _result_field(result, "text_excerpt", "snippet", "summary", "description", "text")
    url = _result_field(result, "post_url", "url", "link")

    parts: list[str] = []
    if title:
        parts.append(f"{index}. {title}")
    else:
        parts.append(f"{index}. Инструкция")
    if snippet:
        parts.append(snippet)
    if url:
        parts.append(url)
    return "\n".join(parts)


def _format_search_results_message(query: str, results: list[Any]) -> str:
    if len(results) == 1:
        header = f"Нашлась инструкция по запросу «{query}»:"
    else:
        header = f"Нашёл несколько инструкций по запросу «{query}»:"
    body = "\n\n".join(_format_search_result_line(index, result) for index, result in enumerate(results, start=1))
    return f"{header}\n\n{body}"


async def send_welcome_once(ctx: Context, user_id: int, chat_id: int) -> bool:
    if await ctx.db.should_send_welcome(user_id):
        await ctx.client.send_message(chat_id, WELCOME_TEXT, reply_markup=consent_keyboard(ctx.privacy_policy_url))
        return True
    return False


async def _is_subscribed(ctx: Context, user_id: int) -> bool:
    chat_ref = _normalize_chat_ref(ctx.required_chat)
    member = await ctx.client.get_chat_member(chat_ref, user_id)
    status = (member.get("status") or "").strip().lower()
    return status in {"member", "administrator", "creator", "restricted"}


async def _send_manager_entrypoint(
    ctx: Context,
    chat_id: int,
    user_id: int,
    username: str,
    first_name: str,
    last_name: str,
) -> None:
    await _track(
        ctx,
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        event="manager_requested",
        status="ok",
        details={"source": "reply_keyboard"},
    )
    await ctx.client.send_message(
        chat_id,
        f"Открыть чат с менеджером: {MANAGER_TG}",
        reply_markup=manager_link_keyboard(),
    )


async def _open_instruction_search(
    ctx: Context,
    chat_id: int,
    user_id: int,
    username: str,
    first_name: str,
    last_name: str,
) -> None:
    await ctx.db.set_user_mode(user_id, ctx.required_chat, USER_MODE_AWAITING_INSTRUCTION_QUERY)
    await _track(
        ctx,
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        event="instruction_search_opened",
        status="ok",
    )
    await ctx.client.send_message(
        chat_id,
        INSTRUCTION_SEARCH_PROMPT_TEXT,
        reply_markup=manager_reply_keyboard(),
    )


async def _run_instruction_search(
    ctx: Context,
    chat_id: int,
    user_id: int,
    username: str,
    first_name: str,
    last_name: str,
    query: str,
) -> None:
    normalized_query = query.strip()
    if not normalized_query:
        await ctx.client.send_message(chat_id, INSTRUCTION_SEARCH_EMPTY_QUERY_TEXT, reply_markup=manager_reply_keyboard())
        return

    await _track(
        ctx,
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        event="instruction_search_submitted",
        status="ok",
        details={"query": normalized_query},
    )

    service = ctx.instruction_search_service
    if service is None:
        await ctx.client.send_message(chat_id, INSTRUCTION_SEARCH_UNAVAILABLE_TEXT, reply_markup=manager_reply_keyboard())
        return

    try:
        results = _coerce_search_results(
            await service.search(INSTRUCTION_SEARCH_PLATFORM, normalized_query, limit=INSTRUCTION_SEARCH_LIMIT)
        )
    except Exception:
        await ctx.client.send_message(chat_id, INSTRUCTION_SEARCH_UNAVAILABLE_TEXT, reply_markup=manager_reply_keyboard())
        return

    if not results:
        await _track(
            ctx,
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            event="instruction_search_not_found",
            status="ok",
            details={"query": normalized_query},
        )
        await ctx.client.send_message(chat_id, INSTRUCTION_SEARCH_NOT_FOUND_TEXT, reply_markup=manager_reply_keyboard())
        return

    await _track(
        ctx,
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        event="instruction_search_found",
        status="ok",
        details={"query": normalized_query, "results_count": len(results)},
    )
    await ctx.db.set_user_mode(user_id, ctx.required_chat, USER_MODE_IDLE)
    await ctx.client.send_message(
        chat_id,
        _format_search_results_message(normalized_query, results),
        reply_markup=manager_reply_keyboard(),
    )


async def handle_message(ctx: Context, message: dict) -> None:
    user = message.get("from") or {}
    chat = message.get("chat") or {}
    raw_text = (message.get("text") or "").strip()
    text = raw_text.lower()
    user_id = user.get("id")
    chat_id = chat.get("id")
    if user_id is None or chat_id is None:
        return

    user_id = int(user_id)
    chat_id = int(chat_id)
    username, first_name, last_name = _user_profile(user)

    if text == MANAGER_BUTTON_TEXT.lower():
        await _send_manager_entrypoint(ctx, chat_id, user_id, username, first_name, last_name)
        return

    if text in {"/start", "start"}:
        await _track(
            ctx,
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            event="start",
            status="received",
        )
        await ctx.db.set_user_mode(user_id, ctx.required_chat, USER_MODE_IDLE)
        if await ctx.db.get_subscribed(user_id, ctx.required_chat):
            await _track(
                ctx,
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                event="menu_open",
                status="ok",
                details={"source": "start_already_authorized"},
            )
            await ctx.client.send_message(chat_id, ALREADY_AUTH_TEXT, reply_markup=manager_reply_keyboard())
            return

        sent = await send_welcome_once(ctx, user_id, chat_id)
        if not sent:
            await ctx.client.send_message(chat_id, "Проверьте сообщение выше и нажмите «Принимаю».")
        return

    if text.startswith("/"):
        return

    is_authorized = await ctx.db.get_subscribed(user_id, ctx.required_chat)
    if not is_authorized:
        await ctx.client.send_message(chat_id, "Нажмите /start, затем подтвердите согласие и подписку.")
        return

    if text == INSTRUCTION_SEARCH_BUTTON_TEXT.lower():
        await _open_instruction_search(ctx, chat_id, user_id, username, first_name, last_name)
        return

    if await ctx.db.get_user_mode(user_id, ctx.required_chat) == USER_MODE_AWAITING_INSTRUCTION_QUERY:
        await _run_instruction_search(ctx, chat_id, user_id, username, first_name, last_name, raw_text)
        return

    await _track(
        ctx,
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        event="menu_open",
        status="ok",
        details={"source": "message_after_subscribed"},
    )
    await ctx.client.send_message(
        chat_id,
        "Я на связи. Используйте кнопки ниже: можно открыть чат с менеджером или найти инструкцию.",
        reply_markup=manager_reply_keyboard(),
    )


async def handle_callback(ctx: Context, callback: dict) -> None:
    callback_id = callback.get("id")
    user = callback.get("from") or {}
    message = callback.get("message") or {}
    user_id = user.get("id")
    chat_id = (message.get("chat") or {}).get("id")
    payload = callback.get("data")
    if callback_id is None or user_id is None or chat_id is None:
        return

    user_id = int(user_id)
    chat_id = int(chat_id)
    username, first_name, last_name = _user_profile(user)

    if payload == "consent_accept":
        await _track(
            ctx,
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            event="consent_accepted",
            status="ok",
        )
        await ctx.db.set_user_mode(user_id, ctx.required_chat, USER_MODE_IDLE)
        await ctx.client.answer_callback_query(callback_id, "Спасибо! Теперь проверим подписку.")
        await ctx.client.send_message(chat_id, CHECK_TEXT, reply_markup=check_subscription_keyboard())
        return

    if payload == "check_subscription":
        await _track(
            ctx,
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            event="subscription_check",
            status="started",
            details={"required_chat": ctx.required_chat},
        )
        try:
            subscribed = await _is_subscribed(ctx, user_id)
        except TelegramApiError:
            await _track(
                ctx,
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                event="subscription_check",
                status="error",
                details={"required_chat": ctx.required_chat},
            )
            await ctx.client.answer_callback_query(callback_id, "Не удалось проверить подписку. Попробуйте ещё раз.")
            await ctx.client.send_message(
                chat_id,
                "Временная ошибка проверки подписки. Нажмите кнопку ещё раз через несколько секунд.",
            )
            return

        await ctx.db.set_subscribed(user_id, ctx.required_chat, subscribed)
        if subscribed:
            await _track(
                ctx,
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                event="subscription_ok",
                status="ok",
                details={"required_chat": ctx.required_chat},
            )
            await _track(
                ctx,
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                event="menu_open",
                status="ok",
                details={"source": "after_subscription_ok"},
            )
            await ctx.db.set_user_mode(user_id, ctx.required_chat, USER_MODE_IDLE)
            await ctx.client.answer_callback_query(callback_id, "Подписка подтверждена")
            await ctx.client.send_message(
                chat_id,
                "Добро пожаловать! Доступ открыт.",
                reply_markup=manager_reply_keyboard(),
            )
        else:
            await _track(
                ctx,
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                event="subscription_failed",
                status="not_member",
                details={"required_chat": ctx.required_chat},
            )
            await ctx.client.answer_callback_query(callback_id, "Подписка не найдена")
            await ctx.client.send_message(
                chat_id,
                "Подписка не найдена. Подпишитесь на канал и проверьте снова.",
                reply_markup=retry_subscription_keyboard(_channel_url(ctx.required_chat)),
            )
