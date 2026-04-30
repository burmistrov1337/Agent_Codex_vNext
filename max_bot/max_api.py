from __future__ import annotations

import asyncio
from typing import Any

import aiohttp


class MaxApiError(RuntimeError):
    pass


class MaxApiClient:
    def __init__(self, access_token: str, base_url: str) -> None:
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=35, connect=10, sock_connect=10, sock_read=30)
            self._session = aiohttp.ClientSession(headers={"Authorization": self.access_token}, timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        session = await self._get_session()
        url = f"{self.base_url}/{path.lstrip('/')}"
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                async with session.request(method, url, params=params, json=json_body) as resp:
                    payload = await resp.json(content_type=None)
                    if resp.status >= 400:
                        raise MaxApiError(f"{method} {path} failed: {resp.status} {payload}")
                    return payload
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                last_error = exc
                if attempt >= retries:
                    raise MaxApiError(f"{method} {path} timeout/network error after {retries} attempts: {exc}") from exc
                await asyncio.sleep(0.8 * attempt)

        raise MaxApiError(f"{method} {path} failed: {last_error}")

    async def get_updates(self, timeout_seconds: int = 25, marker: str | None = None, limit: int = 50) -> dict[str, Any]:
        params: dict[str, Any] = {"timeout": timeout_seconds, "limit": limit}
        if marker:
            params["marker"] = marker
        return await self._request_json("GET", "/updates", params=params)

    async def create_subscription(
        self,
        url: str,
        *,
        update_types: list[str] | None = None,
        secret: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"url": url}
        if update_types:
            body["update_types"] = update_types
        if secret:
            body["secret"] = secret
        return await self._request_json("POST", "/subscriptions", json_body=body)

    async def get_subscriptions(self) -> dict[str, Any]:
        return await self._request_json("GET", "/subscriptions")

    async def delete_subscription(self, url: str | None = None) -> dict[str, Any]:
        params = {"url": url} if url else None
        return await self._request_json("DELETE", "/subscriptions", params=params)

    async def get_chat(self, chat_id: int) -> dict[str, Any]:
        return await self._request_json("GET", f"/chats/{chat_id}")

    async def get_messages(
        self,
        *,
        chat_id: int | None = None,
        message_ids: list[str] | None = None,
        from_ts: int | None = None,
        to_ts: int | None = None,
        count: int = 50,
    ) -> dict[str, Any]:
        if chat_id is None and not message_ids:
            raise ValueError("Provide chat_id or message_ids")
        params: dict[str, Any] = {"count": count}
        if chat_id is not None:
            params["chat_id"] = chat_id
        if message_ids:
            params["message_ids"] = ",".join(message_ids)
        if from_ts is not None:
            params["from"] = from_ts
        if to_ts is not None:
            params["to"] = to_ts
        return await self._request_json("GET", "/messages", params=params)

    async def send_message(
        self,
        text: str,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if (user_id is None) == (chat_id is None):
            raise ValueError("Provide exactly one of user_id/chat_id")
        params: dict[str, Any] = {"user_id": user_id} if user_id is not None else {"chat_id": chat_id}
        body: dict[str, Any] = {"text": text}
        if attachments is not None:
            body["attachments"] = attachments
        return await self._request_json("POST", "/messages", params=params, json_body=body)

    async def answer_callback(self, callback_id: str, notification: str) -> dict[str, Any]:
        return await self._request_json(
            "POST",
            "/answers",
            params={"callback_id": callback_id},
            json_body={"notification": notification},
        )

    async def is_user_member(self, chat_id: int, user_id: int) -> bool:
        payload = await self._request_json(
            "GET",
            f"/chats/{chat_id}/members",
            params={"user_ids": str(user_id)},
        )
        members = payload.get("members") or payload.get("items") or payload.get("data") or []
        if isinstance(members, dict):
            members = [members]
        for item in members:
            candidate = item.get("user_id") or (item.get("user") or {}).get("id")
            if str(candidate) == str(user_id):
                return True
        return False
