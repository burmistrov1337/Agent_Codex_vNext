from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials
import requests


_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetsWorkbook:
    def __init__(self, spreadsheet_id: str, service_account_file: str) -> None:
        self.spreadsheet_id = spreadsheet_id.strip()
        self.service_account_file = service_account_file.strip()
        self.enabled = bool(self.spreadsheet_id and self.service_account_file and Path(self.service_account_file).exists())
        self._session: AuthorizedSession | None = None

    def _get_session(self) -> AuthorizedSession:
        if not self.enabled:
            raise RuntimeError("Google Sheets workbook is not configured")
        if self._session is None:
            credentials = Credentials.from_service_account_file(self.service_account_file, scopes=_SCOPES)
            self._session = AuthorizedSession(credentials)
        return self._session

    def _spreadsheet_url(self, suffix: str = "") -> str:
        return f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}{suffix}"

    def _request(self, method: str, suffix: str = "", *, json_body: dict[str, Any] | None = None, timeout: int = 30):
        last_exc: Exception | None = None
        response = None
        for attempt in range(3):
            try:
                response = self._get_session().request(
                    method,
                    self._spreadsheet_url(suffix),
                    json=json_body,
                    timeout=timeout,
                )
                return response
            except requests.RequestException as exc:
                last_exc = exc
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        if last_exc:
            raise last_exc
        raise RuntimeError("Google Sheets request failed unexpectedly")

    def get_sheet_titles(self) -> set[str]:
        response = self._request("GET", timeout=30)
        if response.status_code >= 400:
            raise RuntimeError(f"Google Sheets metadata read failed: {response.status_code} {response.text[:500]}")
        payload = response.json()
        sheets = payload.get("sheets") or []
        return {str((item.get('properties') or {}).get('title') or "") for item in sheets}

    def batch_update(self, requests: list[dict[str, Any]]) -> None:
        response = self._request("POST", ":batchUpdate", json_body={"requests": requests}, timeout=30)
        if response.status_code >= 400:
            raise RuntimeError(f"Google Sheets batchUpdate failed: {response.status_code} {response.text[:500]}")

    def ensure_sheets(self, sheets_with_headers: dict[str, list[str]]) -> None:
        existing = self.get_sheet_titles()
        requests: list[dict[str, Any]] = []
        for title in sheets_with_headers:
            if title not in existing:
                requests.append({"addSheet": {"properties": {"title": title}}})
        if requests:
            self.batch_update(requests)
        for title, headers in sheets_with_headers.items():
            values = self.read_rows(title)
            if not values:
                self.append_rows(title, [headers])

    def read_rows(self, sheet_name: str) -> list[list[str]]:
        response = self._request("GET", f"/values/{sheet_name}", timeout=30)
        if response.status_code >= 400:
            raise RuntimeError(f"Google Sheets read failed: {response.status_code} {response.text[:500]}")
        payload = response.json()
        values = payload.get("values") or []
        return [[str(cell) for cell in row] for row in values]

    def clear_sheet(self, sheet_name: str) -> None:
        response = self._request("POST", f"/values/{sheet_name}:clear", json_body={}, timeout=30)
        if response.status_code >= 400:
            raise RuntimeError(f"Google Sheets clear failed: {response.status_code} {response.text[:500]}")

    def append_rows(self, sheet_name: str, rows: list[list[Any]]) -> None:
        response = self._request(
            "POST",
            f"/values/{sheet_name}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
            json_body={"values": rows},
            timeout=45,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Google Sheets append failed: {response.status_code} {response.text[:500]}")

    def rewrite_sheet(self, sheet_name: str, headers: list[str], rows: list[list[Any]]) -> None:
        self.clear_sheet(sheet_name)
        self.append_rows(sheet_name, [headers] + rows)

    @staticmethod
    def json_cell(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
