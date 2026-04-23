from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials


LOGGER = logging.getLogger(__name__)
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_COLUMNS = [
    "timestamp_utc",
    "messenger",
    "bot_env",
    "user_id",
    "username",
    "first_name",
    "last_name",
    "event",
    "status",
    "details_json",
]


@dataclass(frozen=True, slots=True)
class AnalyticsEvent:
    messenger: str
    bot_env: str
    user_id: int | str
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    event: str = ""
    status: str = ""
    details: dict[str, Any] | None = None


class BotAnalytics:
    def __init__(self, spreadsheet_id: str | None, service_account_file: str | None) -> None:
        self.spreadsheet_id = (spreadsheet_id or "").strip()
        self.service_account_file = (service_account_file or "").strip()
        self.enabled = bool(self.spreadsheet_id and self.service_account_file and Path(self.service_account_file).exists())
        self._session: AuthorizedSession | None = None
        self._header_written: set[str] = set()

    def _get_session(self) -> AuthorizedSession:
        if self._session is None:
            credentials = Credentials.from_service_account_file(self.service_account_file, scopes=_SCOPES)
            self._session = AuthorizedSession(credentials)
        return self._session

    def _append_values(self, sheet_name: str, values: list[list[str]]) -> None:
        quoted_range = quote(f"{sheet_name}!A:J", safe="!:")
        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values/"
            f"{quoted_range}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS"
        )
        response = self._get_session().post(url, json={"values": values}, timeout=20)
        if response.status_code >= 400:
            raise RuntimeError(f"Google Sheets append failed: {response.status_code} {response.text[:500]}")

    def _ensure_header(self, sheet_name: str) -> None:
        if sheet_name in self._header_written:
            return
        quoted_range = quote(f"{sheet_name}!A1:J1", safe="!:")
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values/{quoted_range}"
        response = self._get_session().get(url, timeout=20)
        if response.status_code >= 400:
            raise RuntimeError(f"Google Sheets read failed: {response.status_code} {response.text[:500]}")
        payload = response.json()
        values = payload.get("values") or []
        if not values:
            self._append_values(sheet_name, [list(_COLUMNS)])
        self._header_written.add(sheet_name)

    @staticmethod
    def _sheet_for_messenger(messenger: str) -> str:
        if messenger.lower() == "max":
            return "MAX"
        if messenger.lower() == "telegram":
            return "TELEGRAM"
        raise ValueError(f"Unsupported messenger: {messenger}")

    @staticmethod
    def _row(event: AnalyticsEvent) -> list[str]:
        now = datetime.now(tz=timezone.utc).isoformat()
        return [
            now,
            event.messenger,
            event.bot_env,
            str(event.user_id),
            event.username or "",
            event.first_name or "",
            event.last_name or "",
            event.event,
            event.status,
            json.dumps(event.details or {}, ensure_ascii=False, separators=(",", ":")),
        ]

    def append_event_sync(self, event: AnalyticsEvent) -> None:
        if not self.enabled:
            return
        sheet_name = self._sheet_for_messenger(event.messenger)
        self._ensure_header(sheet_name)
        self._append_values(sheet_name, [self._row(event)])

    async def append_event(self, event: AnalyticsEvent) -> None:
        if not self.enabled:
            return
        try:
            await asyncio.to_thread(self.append_event_sync, event)
        except Exception as exc:
            LOGGER.warning("Analytics append failed: %s", exc)

    def append_event_nowait(self, event: AnalyticsEvent) -> None:
        if not self.enabled:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.append_event(event))
