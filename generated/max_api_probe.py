import os
import asyncio
from max_bot.max_api import MaxApiClient

async def main():
    token = os.environ["MAX_ACCESS_TOKEN"]
    base = os.environ.get("MAX_API_BASE_URL", "https://platform-api.max.ru")
    chat_id = int(os.environ["MAX_REQUIRED_CHAT_ID"])
    client = MaxApiClient(token, base)
    seen = set()
    to_ts = None
    try:
        for b in range(1, 9):
            payload = await client.get_messages(chat_id=chat_id, count=100, to_ts=to_ts)
            msgs = payload.get("messages") or payload.get("items") or []
            if isinstance(msgs, dict):
                msgs = [msgs]

            mids = []
            timestamps = []
            badd_hits = 0
            for msg in msgs:
                body = msg.get("body") or {}
                mid = str(body.get("mid") or msg.get("mid") or msg.get("id") or "")
                if mid:
                    mids.append(mid)

                ts = msg.get("timestamp")
                if isinstance(ts, (int, float)):
                    timestamps.append(int(ts))

                text = body.get("text") if isinstance(body, dict) else ""
                if isinstance(text, list):
                    parts = []
                    for item in text:
                        if isinstance(item, str):
                            parts.append(item)
                        elif isinstance(item, dict):
                            parts.append(str(item.get("text") or ""))
                    text = "".join(parts)
                text_low = str(text or "").lower()
                if ("badd" in text_low) or ("????" in text_low) or ("????" in text_low):
                    badd_hits += 1

            fresh = [m for m in mids if m not in seen]
            for m in mids:
                seen.add(m)

            oldest = min(timestamps) if timestamps else None
            next_to = (oldest - 1) if oldest else None
            print(f"batch={b} msgs={len(msgs)} unique_total={len(seen)} fresh={len(fresh)} to_in={to_ts} oldest={oldest} next_to={next_to} badd_hits={badd_hits}")

            if not timestamps:
                break
            if to_ts is not None and next_to is not None and next_to >= to_ts:
                break
            to_ts = next_to
    finally:
        await client.close()

asyncio.run(main())
