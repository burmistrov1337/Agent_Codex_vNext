from __future__ import annotations

import asyncio
import json

from .config import load_settings
from .max_api import MaxApiClient


async def run() -> None:
    s = load_settings()
    client = MaxApiClient(s.max_access_token, s.max_api_base_url)
    payload = await client.get_updates(timeout_seconds=2, limit=50)
    await client.close()
    updates = payload.get("updates") or payload.get("items") or []
    if isinstance(updates, dict):
        updates = [updates]

    found = {}
    for update in updates:
        msg = update.get("message") or {}
        callback = update.get("callback") or {}
        for chat in (msg.get("recipient") or {}, callback.get("message", {}).get("recipient") or {}):
            chat_id = chat.get("chat_id")
            if chat_id is not None:
                found[str(chat_id)] = {"chat_id": chat_id, "chat_type": chat.get("chat_type")}

    if not found:
        print("No chat ids found in updates.")
        return
    print("Discovered chats:")
    for row in found.values():
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(run())

