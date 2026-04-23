from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Protocol, Sequence

from bot_analytics import AnalyticsEvent, BotAnalytics

from .database import Database
from .keyboards import check_subscription_keyboard, consent_keyboard, manager_keyboard, retry_subscription_keyboard
from .max_api import MaxApiClient

CHANNEL_URL = "https://max.ru/id5433976641_biz"
MANAGER_PHONE = "+79132003939"
SEARCH_PROMPT = "Введите название актива, синоним или INCI."
SEARCH_UNAVAILABLE_TEXT = "Поиск инструкций пока недоступен. Пока можно написать менеджеру."


class InstructionSearchService(Protocol):
    async def search(self, platform: str, query: str, limit: int = 3) -> Sequence[object]:
        ...


@dataclass(slots=True)
class Context:
    client: MaxApiClient
    db: Database
    required_chat_id: int
    privacy_policy_url: str
    bot_env: str
    analytics: BotAnalytics
    instruction_search_service: InstructionSearchService | None = None


WELCOME_TEXT = (
    "Здравствуйте! Мы рады, что вы выбрали наш магазин ADK cosmetics!\n\n"
    "Для продолжения работы нам необходимо ваше согласие.\n"
    'Нажимая кнопку "Принимаю", вы подтверждаете ознакомление с Политикой конфиденциальности '
    "и даете согласие на обработку персональных данных."
)

CHECK_TEXT = (
    "Отлично! Теперь проверим подписку на наш канал, где собраны инструкции, "
    "авторские рецепты на основе компонентов из нашего магазина и консультации технолога."
)


def _profile_from_user(user: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(user.get("username") or user.get("name") or ""),
        str(user.get("first_name") or ""),
        str(user.get("last_name") or ""),
    )


def _result_field(result: object, *names: str) -> str:
    if isinstance(result, dict):
        for name in names:
            value = result.get(name)
            if value:
                return str(value)
        return ""
    for name in names:
        value = getattr(result, name, None)
        if value:
            return str(value)
    return ""


_MAX_POST_URL_RE = re.compile(r"^https?://(?:www\.)?max\.ru/id[^/]+/[A-Za-z0-9_-]+$", re.IGNORECASE)


def _is_max_post_url(url: str) -> bool:
    return bool(_MAX_POST_URL_RE.match((url or "").strip()))


def _format_search_results(results: Sequence[object]) -> str:
    items: list[str] = []
    for index, result in enumerate(results, start=1):
        title = _result_field(result, "display_title", "title", "active_name", "name") or f"Инструкция {index}"
        url = _result_field(result, "post_url", "url", "link")
        summary = _result_field(result, "text_excerpt", "summary", "description", "snippet")

        line = f"{index}. {title}"
        if summary:
            line = f"{line}\n{summary}"
        if _is_max_post_url(url):
            line = f"{line}\n{url}"
        items.append(line)

    if len(results) == 1:
        return f"Нашёл инструкцию:\n\n{items[0]}"
    return "Нашёл несколько вариантов:\n\n" + "\n\n".join(items)


async def _track(
    ctx: Context,
    *,
    user_id: int,
    username: str,
    first_name: str,
    last_name: str,
    event: str,
    status: str,
    details: dict[str, Any] | None = None,
) -> None:
    ctx.analytics.append_event_nowait(
        AnalyticsEvent(
            messenger="max",
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


async def send_welcome_once(ctx: Context, user_id: int) -> None:
    if await ctx.db.should_send_welcome(user_id):
        await ctx.client.send_message(
            WELCOME_TEXT,
            user_id=user_id,
            attachments=consent_keyboard(ctx.privacy_policy_url),
        )


async def _send_authorized_menu(ctx: Context, user_id: int, text: str) -> None:
    await ctx.client.send_message(text, user_id=user_id, attachments=manager_keyboard())


async def _open_instruction_search(
    ctx: Context,
    *,
    user_id: int,
    username: str,
    first_name: str,
    last_name: str,
) -> None:
    await ctx.db.set_mode(user_id, ctx.required_chat_id, "awaiting_instruction_query")
    await _track(
        ctx,
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        event="instruction_search_opened",
        status="ok",
    )
    await ctx.client.send_message(SEARCH_PROMPT, user_id=user_id)


async def _handle_instruction_query(
    ctx: Context,
    *,
    user_id: int,
    username: str,
    first_name: str,
    last_name: str,
    query: str,
) -> None:
    await _track(
        ctx,
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        event="instruction_search_submitted",
        status="ok",
        details={"query": query},
    )

    service = ctx.instruction_search_service
    if service is None:
        await ctx.client.send_message(SEARCH_UNAVAILABLE_TEXT, user_id=user_id, attachments=manager_keyboard())
        return

    try:
        results = list(await service.search("max", query, limit=3))
    except Exception:
        await ctx.client.send_message(SEARCH_UNAVAILABLE_TEXT, user_id=user_id, attachments=manager_keyboard())
        return
    if results:
        await ctx.db.set_mode(user_id, ctx.required_chat_id, "idle")
        await _track(
            ctx,
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            event="instruction_search_found",
            status="ok",
            details={"query": query, "results_count": len(results)},
        )
        await ctx.client.send_message(_format_search_results(results), user_id=user_id, attachments=manager_keyboard())
        return

    await _track(
        ctx,
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        event="instruction_search_not_found",
        status="empty",
        details={"query": query},
    )
    await ctx.client.send_message(
        "Не нашёл инструкцию. Попробуйте другое название, синоним или INCI. Если нужно, можно написать менеджеру.",
        user_id=user_id,
        attachments=manager_keyboard(),
    )


async def handle_bot_started(ctx: Context, update: dict[str, Any]) -> None:
    user = update.get("user") or {}
    uid = user.get("user_id") or user.get("id")
    if uid is None:
        return
    try:
        user_id = int(uid)
    except ValueError:
        return
    username, first_name, last_name = _profile_from_user(user)
    await _track(
        ctx,
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        event="start",
        status="received",
        details={"source": "bot_started"},
    )
    await send_welcome_once(ctx, user_id)


def _message_user_id(message: dict[str, Any]) -> int | None:
    sender = message.get("sender") or {}
    user = message.get("user") or {}
    candidate = sender.get("user_id") or sender.get("id") or user.get("user_id") or user.get("id") or message.get("sender_id")
    if candidate is None:
        return None
    try:
        return int(candidate)
    except ValueError:
        return None


def _message_user(message: dict[str, Any]) -> dict[str, Any]:
    sender = message.get("sender") or {}
    user = message.get("user") or {}
    return user if user else sender


def _message_text(message: dict[str, Any]) -> str:
    body = message.get("body") or {}
    text = body.get("text")
    if isinstance(text, str):
        return text.strip()
    raw = message.get("text")
    if isinstance(raw, str):
        return raw.strip()
    return ""


async def handle_message(ctx: Context, update: dict[str, Any]) -> None:
    message = update.get("message") or {}
    uid = _message_user_id(message)
    if uid is None:
        return
    username, first_name, last_name = _profile_from_user(_message_user(message))
    raw_text = _message_text(message)
    text = raw_text.lower()
    subscribed = await ctx.db.get_subscribed(uid, ctx.required_chat_id)

    if text in {"/start", "start"}:
        if subscribed:
            await ctx.db.set_mode(uid, ctx.required_chat_id, "idle")
            await _track(
                ctx,
                user_id=uid,
                username=username,
                first_name=first_name,
                last_name=last_name,
                event="menu_open",
                status="ok",
                details={"source": "start_already_authorized"},
            )
            await _send_authorized_menu(ctx, uid, "С возвращением! Вы уже прошли проверку, доступ открыт.")
            return
        await _track(
            ctx,
            user_id=uid,
            username=username,
            first_name=first_name,
            last_name=last_name,
            event="start",
            status="received",
            details={"source": "message_start"},
        )
        await send_welcome_once(ctx, uid)
        return

    if not subscribed:
        await ctx.client.send_message("Нажмите /start, затем подтвердите согласие и подписку.", user_id=uid)
        return

    mode = await ctx.db.get_mode(uid, ctx.required_chat_id)
    if mode == "awaiting_instruction_query":
        if not raw_text:
            await ctx.client.send_message(SEARCH_PROMPT, user_id=uid)
            return
        await _handle_instruction_query(
            ctx,
            user_id=uid,
            username=username,
            first_name=first_name,
            last_name=last_name,
            query=raw_text,
        )
        return

    await _track(
        ctx,
        user_id=uid,
        username=username,
        first_name=first_name,
        last_name=last_name,
        event="menu_open",
        status="ok",
        details={"source": "message_after_subscribed"},
    )
    await _send_authorized_menu(ctx, uid, "Я на связи. Выберите действие в меню ниже.")


async def handle_callback(ctx: Context, update: dict[str, Any]) -> None:
    callback = update.get("callback") or {}
    callback_id = callback.get("callback_id")
    user = callback.get("user") or {}
    uid = user.get("user_id") or user.get("id")
    payload = callback.get("payload")
    if callback_id is None or uid is None:
        return
    try:
        user_id = int(uid)
    except ValueError:
        return
    username, first_name, last_name = _profile_from_user(user)

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
        await ctx.client.answer_callback(str(callback_id), "Спасибо! Теперь проверим подписку.")
        await ctx.client.send_message(CHECK_TEXT, user_id=user_id, attachments=check_subscription_keyboard())
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
            details={"required_chat_id": ctx.required_chat_id},
        )
        subscribed = await ctx.client.is_user_member(ctx.required_chat_id, user_id)
        await ctx.db.set_subscribed(user_id, ctx.required_chat_id, subscribed)
        if subscribed:
            await ctx.db.set_mode(user_id, ctx.required_chat_id, "idle")
            await _track(
                ctx,
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                event="subscription_ok",
                status="ok",
                details={"required_chat_id": ctx.required_chat_id},
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
            await ctx.client.answer_callback(str(callback_id), "Подписка подтверждена")
            await _send_authorized_menu(ctx, user_id, "Добро пожаловать! Доступ открыт.")
        else:
            await _track(
                ctx,
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                event="subscription_failed",
                status="not_member",
                details={"required_chat_id": ctx.required_chat_id},
            )
            await ctx.client.answer_callback(str(callback_id), "Подписка не найдена")
            await ctx.client.send_message(
                "Подписка не найдена. Подпишитесь на канал и проверьте снова.",
                user_id=user_id,
                attachments=retry_subscription_keyboard(CHANNEL_URL),
            )
        return

    if payload == "instruction_search_open":
        if not await ctx.db.get_subscribed(user_id, ctx.required_chat_id):
            await ctx.client.answer_callback(str(callback_id), "Сначала подтвердите подписку")
            return
        await ctx.client.answer_callback(str(callback_id), "Введите запрос")
        await _open_instruction_search(
            ctx,
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        return

    if payload == "manager_contact":
        await _track(
            ctx,
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            event="manager_requested",
            status="ok",
        )
        await ctx.client.answer_callback(str(callback_id), "Передаю контакт менеджера")
        await ctx.client.send_message(f"Связь с менеджером: {MANAGER_PHONE}", user_id=user_id)
