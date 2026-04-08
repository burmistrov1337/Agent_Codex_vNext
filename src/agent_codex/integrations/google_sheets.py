from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from ..config import Settings


class GoogleSheetsError(RuntimeError):
    pass


@dataclass(slots=True)
class GoogleSheetsClient:
    spreadsheet_id: str
    service_account_file: Path | None = None
    service_account_json: str | None = None
    timeout_seconds: int = 30
    _credentials: Any | None = field(default=None, init=False, repr=False)

    @property
    def spreadsheet_url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/edit"

    def get_spreadsheet(self) -> dict[str, Any]:
        return self._request_json("GET", f"/spreadsheets/{self.spreadsheet_id}")

    def get_values(self, a1_range: str) -> list[list[str]]:
        normalized_range = _normalize_a1_range(a1_range)
        payload = self._request_json(
            "GET",
            f"/spreadsheets/{self.spreadsheet_id}/values/{_quote_range(normalized_range)}",
        )
        return payload.get("values", [])

    def write_values(self, a1_range: str, values: list[list[Any]], *, user_entered: bool = False) -> dict[str, Any]:
        normalized_range = _normalize_a1_range(a1_range)
        return self._request_json(
            "PUT",
            f"/spreadsheets/{self.spreadsheet_id}/values/{_quote_range(normalized_range)}",
            params={"valueInputOption": "USER_ENTERED" if user_entered else "RAW"},
            json_payload={"range": normalized_range, "majorDimension": "ROWS", "values": values},
        )

    def batch_update_values(self, data: list[dict[str, Any]], *, user_entered: bool = False) -> dict[str, Any]:
        normalized_data = [{**item, "range": _normalize_a1_range(str(item["range"]))} for item in data]
        return self._request_json(
            "POST",
            f"/spreadsheets/{self.spreadsheet_id}/values:batchUpdate",
            json_payload={
                "valueInputOption": "USER_ENTERED" if user_entered else "RAW",
                "data": normalized_data,
            },
        )

    def batch_clear(self, ranges: list[str]) -> dict[str, Any]:
        normalized_ranges = [_normalize_a1_range(item) for item in ranges]
        return self._request_json(
            "POST",
            f"/spreadsheets/{self.spreadsheet_id}/values:batchClear",
            json_payload={"ranges": normalized_ranges},
        )

    def batch_update(self, requests: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request_json(
            "POST",
            f"/spreadsheets/{self.spreadsheet_id}:batchUpdate",
            json_payload={"requests": requests},
        )

    def ensure_sheets(self, titles: list[str] | tuple[str, ...]) -> dict[str, int]:
        metadata = self.get_spreadsheet()
        sheets = metadata.get("sheets", [])
        title_to_id = {
            item.get("properties", {}).get("title"): item.get("properties", {}).get("sheetId")
            for item in sheets
            if item.get("properties", {}).get("title")
        }
        requests: list[dict[str, Any]] = []
        default_title = next(
            (
                title
                for title in title_to_id
                if title in {"Sheet1", "Лист1", "Sheet", "Лист"} and "Панель" not in title_to_id
            ),
            None,
        )
        if default_title:
            requests.append(
                {
                    "updateSheetProperties": {
                        "properties": {"sheetId": title_to_id[default_title], "title": "Панель"},
                        "fields": "title",
                    }
                }
            )
        for title in titles:
            if title not in title_to_id and not (default_title and title == "Панель"):
                requests.append({"addSheet": {"properties": {"title": title}}})
        if requests:
            self.batch_update(requests)
            metadata = self.get_spreadsheet()
            sheets = metadata.get("sheets", [])
            title_to_id = {
                item.get("properties", {}).get("title"): item.get("properties", {}).get("sheetId")
                for item in sheets
                if item.get("properties", {}).get("title")
            }
        return {title: int(title_to_id[title]) for title in titles if title in title_to_id}

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = self._access_token()
        url = f"https://sheets.googleapis.com/v4{path}"
        if params:
            url = f"{url}?{parse.urlencode(params, doseq=True)}"
        payload = None
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        if json_payload is not None:
            payload = json.dumps(json_payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = request.Request(url=url, method=method.upper(), data=payload, headers=headers)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GoogleSheetsError(f"Google Sheets API HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise GoogleSheetsError(f"Google Sheets API connection error: {exc.reason}") from exc

    def _access_token(self) -> str:
        credentials = self._load_credentials()
        try:
            from google.auth.transport.requests import Request as GoogleAuthRequest
        except ModuleNotFoundError as exc:
            raise GoogleSheetsError(
                "Google Sheets support requires the google-auth package."
            ) from exc
        credentials.refresh(GoogleAuthRequest())
        token = getattr(credentials, "token", None)
        if not token:
            raise GoogleSheetsError("Google Sheets credentials did not yield an access token.")
        return token

    def _load_credentials(self):
        if self._credentials is not None:
            return self._credentials
        try:
            from google.oauth2 import service_account
        except ModuleNotFoundError as exc:
            raise GoogleSheetsError(
                "Google Sheets support requires the google-auth package."
            ) from exc

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        if self.service_account_json:
            info = json.loads(self.service_account_json)
            self._credentials = service_account.Credentials.from_service_account_info(info, scopes=scopes)
        elif self.service_account_file:
            self._credentials = service_account.Credentials.from_service_account_file(
                str(self.service_account_file),
                scopes=scopes,
            )
        else:
            raise GoogleSheetsError(
                "GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON must be configured."
            )
        return self._credentials


def build_google_sheets_client(settings: Settings) -> GoogleSheetsClient:
    if not settings.google_sheets_spreadsheet_id:
        raise RuntimeError("GOOGLE_SHEETS_SPREADSHEET_ID is not configured.")
    return GoogleSheetsClient(
        spreadsheet_id=settings.google_sheets_spreadsheet_id,
        service_account_file=settings.google_service_account_file,
        service_account_json=settings.google_service_account_json,
        timeout_seconds=max(settings.wb_api_timeout_seconds, 180),
    )


def _quote_range(a1_range: str) -> str:
    return parse.quote(a1_range, safe="!:$,")


def _normalize_a1_range(a1_range: str) -> str:
    normalized = a1_range.strip()
    if "!" not in normalized:
        return normalized
    sheet_name, cell_range = normalized.split("!", 1)
    if not (sheet_name.startswith("'") and sheet_name.endswith("'")) and not re.fullmatch(r"[A-Za-z0-9_]+", sheet_name):
        sheet_name = "'" + sheet_name.replace("'", "''") + "'"
    return f"{sheet_name}!{cell_range}"
