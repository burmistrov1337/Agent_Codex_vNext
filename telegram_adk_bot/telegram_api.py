from __future__ import annotations

import asyncio
from typing import Any

import aiohttp


class TelegramApiError(RuntimeError):
    pass


class TelegramApiClient:
    def __init__(self, token: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=35, connect=10, sock_connect=10, sock_read=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(self, method: str, api_method: str, *, params: dict[str, Any] | None = None, json_body: dict[str, Any] | None = None, retries: int = 3) -> dict[str, Any]:
        session = await self._get_session()
        url = f"{self.base_url}/{api_method}"
        for attempt in range(1, retries + 1):
            try:
                async with session.request(method, url, params=params, json=json_body) as resp:
                    payload = await resp.json(content_type=None)
                    if resp.status >= 400:
                        raise TelegramApiError(f"{api_method} http {resp.status}: {payload}")
                    if not payload.get("ok", False):
                        raise TelegramApiError(f"{api_method} failed: {payload}")
                    return payload["result"]
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                if attempt >= retries:
                    raise TelegramApiError(f"{api_method} timeout/network error after {retries} attempts: {exc}") from exc
                await asyncio.sleep(0.8 * attempt)
        raise TelegramApiError(f"{api_method} failed")

    async def get_updates(self, offset: int | None, timeout_seconds: int = 25) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"timeout": timeout_seconds, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            params["offset"] = offset
        return await self._request("GET", "getUpdates", params=params)

    async def send_message(self, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            body["reply_markup"] = reply_markup
        return await self._request("POST", "sendMessage", json_body=body)

    async def answer_callback_query(self, callback_query_id: str, text: str) -> dict[str, Any]:
        body = {"callback_query_id": callback_query_id, "text": text, "show_alert": False}
        return await self._request("POST", "answerCallbackQuery", json_body=body)

    async def get_chat_member(self, chat_id: str, user_id: int) -> dict[str, Any]:
        return await self._request("GET", "getChatMember", params={"chat_id": chat_id, "user_id": user_id})

