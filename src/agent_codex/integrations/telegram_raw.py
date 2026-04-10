from __future__ import annotations

import json
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..errors import ApiError


class TelegramNotifyError(ApiError):
    pass


@dataclass(slots=True)
class TelegramChatPreview:
    chat_id: str
    chat_type: str
    title: str | None = None
    username: str | None = None


def resolve_latest_chat(bot_token: str, timeout_seconds: int = 30) -> TelegramChatPreview:
    updates = get_updates(bot_token, timeout_seconds=timeout_seconds)
    if not updates:
        raise TelegramNotifyError(
            "Бот пока не видит сообщений. Открой диалог с ботом, отправь /start или любое сообщение и повтори."
        )

    for update in reversed(updates):
        message = update.get("message") or update.get("edited_message")
        if not message:
            continue
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            continue
        return TelegramChatPreview(
            chat_id=str(chat_id),
            chat_type=str(chat.get("type") or "unknown"),
            title=chat.get("title"),
            username=chat.get("username"),
        )

    raise TelegramNotifyError("Не удалось определить chat_id из обновлений Telegram.")


def get_updates(
    bot_token: str,
    *,
    offset: int | None = None,
    timeout_seconds: int = 30,
    limit: int = 20,
) -> list[dict]:
    data: dict[str, int] = {
        "timeout": max(0, int(timeout_seconds)),
        "limit": max(1, min(int(limit), 100)),
    }
    if offset is not None:
        data["offset"] = int(offset)
    payload = _telegram_request(
        bot_token,
        "getUpdates",
        data=data,
        timeout_seconds=max(5, int(timeout_seconds) + 5),
    )
    result = payload.get("result") or []
    if not isinstance(result, list):
        raise TelegramNotifyError("Telegram getUpdates вернул неожиданный формат данных.")
    return result


def get_file_info(bot_token: str, file_id: str, timeout_seconds: int = 30) -> dict:
    payload = _telegram_request(
        bot_token,
        "getFile",
        data={"file_id": file_id},
        timeout_seconds=timeout_seconds,
    )
    result = payload.get("result") or {}
    if not isinstance(result, dict) or not result.get("file_path"):
        raise TelegramNotifyError(f"Telegram getFile не вернул file_path для file_id={file_id}.")
    return result


def download_file(
    bot_token: str,
    file_path: str,
    destination: str | Path,
    timeout_seconds: int = 60,
) -> Path:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url=f"https://api.telegram.org/file/bot{bot_token}/{file_path}",
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": "Agent_Codex_vNext/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            target.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise TelegramNotifyError(f"Telegram file download HTTP {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise TelegramNotifyError(f"Telegram file download network error: {exc.reason}") from exc
    return target


def send_message(
    bot_token: str,
    chat_id: str,
    text: str,
    timeout_seconds: int = 30,
    reply_to_message_id: int | None = None,
) -> dict:
    data: dict[str, str | int] = {
        "chat_id": chat_id,
        "text": text,
    }
    if reply_to_message_id is not None:
        data["reply_to_message_id"] = int(reply_to_message_id)
    return _telegram_request(
        bot_token,
        "sendMessage",
        data=data,
        timeout_seconds=timeout_seconds,
    )


def send_document(
    bot_token: str,
    chat_id: str,
    document_path: str | Path,
    caption: str | None = None,
    timeout_seconds: int = 60,
    reply_to_message_id: int | None = None,
) -> dict:
    file_path = Path(document_path)
    if not file_path.exists():
        raise TelegramNotifyError(f"Файл для отправки в Telegram не найден: {file_path}")

    boundary = f"AgentCodex{uuid.uuid4().hex}"
    payload = bytearray()
    fields: dict[str, str | int] = {"chat_id": chat_id}
    if caption:
        fields["caption"] = caption
    if reply_to_message_id is not None:
        fields["reply_to_message_id"] = int(reply_to_message_id)

    for key, value in fields.items():
        payload.extend(f"--{boundary}\r\n".encode("utf-8"))
        payload.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        payload.extend(str(value).encode("utf-8"))
        payload.extend(b"\r\n")

    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    payload.extend(f"--{boundary}\r\n".encode("utf-8"))
    payload.extend(
        (
            f'Content-Disposition: form-data; name="document"; filename="{file_path.name}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8")
    )
    payload.extend(file_path.read_bytes())
    payload.extend(b"\r\n")
    payload.extend(f"--{boundary}--\r\n".encode("utf-8"))

    return _telegram_request_bytes(
        bot_token,
        "sendDocument",
        data=bytes(payload),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        timeout_seconds=timeout_seconds,
    )


def _telegram_request(
    bot_token: str,
    method: str,
    data: dict | None = None,
    timeout_seconds: int = 30,
) -> dict:
    encoded = None
    headers = {
        "Accept": "application/json",
        "User-Agent": "Agent_Codex_vNext/1.0",
    }
    if data is not None:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(
        url=f"https://api.telegram.org/bot{bot_token}/{method}",
        data=encoded,
        headers=headers,
        method="POST" if encoded is not None else "GET",
    )
    return _perform_request(request, timeout_seconds=timeout_seconds)


def _telegram_request_bytes(
    bot_token: str,
    method: str,
    data: bytes,
    headers: dict[str, str] | None = None,
    timeout_seconds: int = 30,
) -> dict:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "Agent_Codex_vNext/1.0",
    }
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(
        url=f"https://api.telegram.org/bot{bot_token}/{method}",
        data=data,
        headers=request_headers,
        method="POST",
    )
    return _perform_request(request, timeout_seconds=timeout_seconds)


def _perform_request(request: urllib.request.Request, timeout_seconds: int = 30) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise TelegramNotifyError(f"Telegram HTTP {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise TelegramNotifyError(f"Telegram network error: {exc.reason}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TelegramNotifyError("Не удалось разобрать ответ Telegram API.") from exc

    if not payload.get("ok", False):
        raise TelegramNotifyError(f"Telegram API вернул ошибку: {payload}")
    return payload
