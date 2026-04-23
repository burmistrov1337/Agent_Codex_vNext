from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from max_bot.config import load_settings
from max_bot.max_api import MaxApiClient
from scripts._env import load_repo_dotenv


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch MAX channel/chat posts for instruction search indexing.")
    parser.add_argument("--app-env", choices=["local", "server"], default="server")
    parser.add_argument("--chat-id", type=int, help="MAX chat/channel id. Defaults to MAX_REQUIRED_CHAT_ID.")
    parser.add_argument("--count", type=int, default=100, help="Messages per request, max 100.")
    parser.add_argument("--batches", type=int, default=10, help="How many backward history batches to fetch.")
    parser.add_argument("--output", help="Optional JSON output path.")
    return parser.parse_args()


def _body_text(body: dict[str, Any] | None) -> str:
    if not isinstance(body, dict):
        return ""
    text = body.get("text")
    if isinstance(text, str):
        return text.strip()
    if isinstance(text, list):
        parts: list[str] = []
        for item in text:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or ""))
        return "".join(parts).strip()
    return ""


def _derive_title(text: str, fallback: str = "") -> str:
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 4:
            return line[:180]
    return fallback[:180]


def _normalize_messages(payload: dict[str, Any], channel_name: str, channel_id: int) -> list[dict[str, Any]]:
    messages = payload.get("messages") or payload.get("items") or []
    if isinstance(messages, dict):
        messages = [messages]
    result: list[dict[str, Any]] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        body = item.get("body") or {}
        text_raw = _body_text(body)
        post_url = str(item.get("url") or "").strip()
        message_id = str(
            item.get("message_id")
            or item.get("mid")
            or body.get("mid")
            or item.get("id")
            or ""
        ).strip()
        timestamp = item.get("timestamp")
        published_at_utc = ""
        if isinstance(timestamp, (int, float)) and timestamp > 0:
            ts_value = float(timestamp)
            if ts_value > 10_000_000_000:
                ts_value /= 1000.0
            published_at_utc = datetime.fromtimestamp(ts_value, tz=timezone.utc).isoformat()
        title = _derive_title(text_raw, fallback=f"{channel_name} #{message_id}")
        result.append(
            {
                "id": message_id,
                "post_id": message_id,
                "url": post_url,
                "post_url": post_url,
                "published_at_utc": published_at_utc,
                "date": published_at_utc,
                "title": title,
                "text": text_raw,
                "caption": text_raw,
                "media": bool(item.get("attachments") or body.get("attachments")),
                "is_instruction": True,
                "is_recipe_candidate": False,
                "extracted_active_primary": "",
                "extracted_inci_primary": "",
                "parse_status": "imported_max_api",
                "source_channel_name": channel_name,
                "source_channel_id": str(channel_id),
            }
        )
    return result


def _extract_message_timestamp(message: dict[str, Any]) -> int | None:
    raw = message.get("timestamp")
    if not isinstance(raw, (int, float)):
        return None
    value = int(raw)
    return value if value > 0 else None


async def _run() -> None:
    args = _args()
    load_repo_dotenv()
    os.environ["MAX_APP_ENV"] = args.app_env
    settings = load_settings()
    chat_id = args.chat_id or settings.max_required_chat_id
    client = MaxApiClient(settings.max_access_token, settings.max_api_base_url)
    try:
        chat_info = await client.get_chat(chat_id)
        channel_name = str(chat_info.get("title") or f"MAX {chat_id}").strip()

        seen_ids: set[str] = set()
        all_items: list[dict[str, Any]] = []
        from_ts: int | None = None

        for _ in range(max(1, args.batches)):
            payload = await client.get_messages(chat_id=chat_id, count=min(max(args.count, 1), 100), from_ts=from_ts)
            batch = _normalize_messages(payload, channel_name, chat_id)
            fresh = [item for item in batch if item.get("id") and item["id"] not in seen_ids]
            for item in fresh:
                seen_ids.add(item["id"])
            if not fresh:
                break
            all_items.extend(fresh)

            raw_messages = payload.get("messages") or payload.get("items") or []
            if isinstance(raw_messages, dict):
                raw_messages = [raw_messages]
            timestamps = [
                ts
                for msg in raw_messages
                if isinstance(msg, dict)
                for ts in [_extract_message_timestamp(msg)]
                if ts is not None
            ]
            if not timestamps:
                break
            # MAX API paginates backwards by `from` (exclusive upper bound).
            oldest = min(timestamps)
            next_from_ts = oldest - 1
            if from_ts is not None and next_from_ts >= from_ts:
                break
            from_ts = next_from_ts

        generated_dir = ROOT / "generated" / "instruction_search" / f"max_export_{datetime.now().strftime('%Y-%m-%d')}"
        generated_dir.mkdir(parents=True, exist_ok=True)
        output_path = Path(args.output) if args.output else (generated_dir / "result.json")
        payload = {
            "platform": "max",
            "channel_name": channel_name,
            "channel_id": str(chat_id),
            "exported_at_utc": datetime.now(tz=timezone.utc).isoformat(),
            "items": all_items,
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Fetched {len(all_items)} MAX posts from chat_id={chat_id} into {output_path}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(_run())
