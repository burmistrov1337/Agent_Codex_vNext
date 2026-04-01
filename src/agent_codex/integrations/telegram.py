from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from .telegram_raw import resolve_latest_chat, send_document, send_message


@dataclass(slots=True)
class TelegramAdapter:
    settings: Settings

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id)

    def send_text(self, text: str) -> dict | None:
        if not self.is_configured:
            return None
        return send_message(
            bot_token=self.settings.telegram_bot_token or "",
            chat_id=self.settings.telegram_chat_id or "",
            text=text,
        )

    def send_file(self, file_path: str | Path, caption: str | None = None) -> dict | None:
        if not self.is_configured:
            return None
        return send_document(
            bot_token=self.settings.telegram_bot_token or "",
            chat_id=self.settings.telegram_chat_id or "",
            document_path=file_path,
            caption=caption,
        )

    def resolve_latest_chat(self) -> str | None:
        if not self.settings.telegram_bot_token:
            return None
        preview = resolve_latest_chat(self.settings.telegram_bot_token)
        return preview.chat_id
