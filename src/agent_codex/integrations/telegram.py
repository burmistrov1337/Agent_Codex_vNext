from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from .telegram_raw import (
    TelegramNotifyError,
    download_file,
    get_file_info,
    get_updates,
    resolve_latest_chat,
    send_document,
    send_message,
)


@dataclass(slots=True)
class TelegramAdapter:
    settings: Settings

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id)

    @property
    def allowed_chat_id(self) -> str | None:
        return self.settings.telegram_allowed_chat_id

    def is_chat_allowed(self, chat_id: str) -> bool:
        return bool(self.allowed_chat_id and str(chat_id) == str(self.allowed_chat_id))

    def send_text(self, text: str, *, reply_to_message_id: int | None = None) -> dict | None:
        if not self.is_configured:
            return None
        return send_message(
            bot_token=self.settings.telegram_bot_token or "",
            chat_id=self.settings.telegram_chat_id or "",
            text=text,
            reply_to_message_id=reply_to_message_id,
        )

    def send_text_to_chat(self, chat_id: str, text: str, *, reply_to_message_id: int | None = None) -> dict | None:
        if not self.settings.telegram_bot_token:
            return None
        return send_message(
            bot_token=self.settings.telegram_bot_token,
            chat_id=str(chat_id),
            text=text,
            reply_to_message_id=reply_to_message_id,
        )

    def send_file(
        self,
        file_path: str | Path,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> dict | None:
        if not self.is_configured:
            return None
        return send_document(
            bot_token=self.settings.telegram_bot_token or "",
            chat_id=self.settings.telegram_chat_id or "",
            document_path=file_path,
            caption=caption,
            reply_to_message_id=reply_to_message_id,
        )

    def send_file_to_chat(
        self,
        chat_id: str,
        file_path: str | Path,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> dict | None:
        if not self.settings.telegram_bot_token:
            return None
        return send_document(
            bot_token=self.settings.telegram_bot_token,
            chat_id=str(chat_id),
            document_path=file_path,
            caption=caption,
            reply_to_message_id=reply_to_message_id,
        )

    def resolve_latest_chat(self) -> str | None:
        if not self.settings.telegram_bot_token:
            return None
        preview = resolve_latest_chat(self.settings.telegram_bot_token)
        return preview.chat_id

    def poll_updates(self, *, offset: int | None = None, limit: int = 20) -> list[dict]:
        if not self.settings.telegram_bot_token:
            return []
        return get_updates(
            self.settings.telegram_bot_token,
            offset=offset,
            timeout_seconds=self.settings.telegram_poll_timeout_seconds,
            limit=limit,
        )

    def fetch_file_info(self, file_id: str) -> dict:
        if not self.settings.telegram_bot_token:
            raise TelegramNotifyError("Telegram bot token is not configured.")
        return get_file_info(self.settings.telegram_bot_token, file_id)

    def download_file(self, file_id: str, destination: str | Path) -> Path:
        info = self.fetch_file_info(file_id)
        file_path = info.get("file_path")
        if not file_path:
            raise TelegramNotifyError(f"Telegram не вернул file_path для file_id={file_id}.")
        return download_file(self.settings.telegram_bot_token or "", file_path, destination)
