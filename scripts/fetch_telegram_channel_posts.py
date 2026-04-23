from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch public Telegram channel posts for instruction search indexing.")
    parser.add_argument("--channel", default="ustore_active", help="Telegram channel username without @.")
    parser.add_argument("--base-url", help="Optional explicit /s/ channel URL.")
    parser.add_argument("--pages", type=int, default=3, help="How many /s/ pages to fetch backwards.")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--output", help="Optional output path.")
    return parser.parse_args()


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _derive_title(text: str, fallback: str) -> str:
    for raw_line in text.splitlines():
        line = " ".join(raw_line.strip().split())
        if len(line) >= 4:
            return line[:180]
    return fallback[:180]


def _message_text(node: Any) -> str:
    text_node = node.select_one(".tgme_widget_message_text")
    if text_node is None:
        return ""
    return text_node.get_text("\n", strip=True)


def _media_flag(node: Any) -> bool:
    selectors = (
        ".tgme_widget_message_photo_wrap",
        ".tgme_widget_message_video_wrap",
        ".tgme_widget_message_video_player",
        ".tgme_widget_message_document",
        ".tgme_widget_message_poll",
        ".tgme_widget_message_album_wrap",
    )
    return any(node.select_one(selector) is not None for selector in selectors)


def _extract_before_token(soup: BeautifulSoup, current_before: str | None) -> str | None:
    more_link = soup.select_one("a.tme_messages_more")
    if more_link is None:
        return None
    href = str(more_link.get("href") or "").strip()
    if not href:
        return None
    before = parse_qs(urlparse(href).query).get("before", [])
    token = before[0].strip() if before else ""
    if not token or token == (current_before or ""):
        return None
    return token


def _parse_page(soup: BeautifulSoup, source_url: str) -> tuple[str, str, list[dict[str, Any]]]:
    username = ""
    title = ""
    title_node = soup.select_one(".tgme_channel_info_header_title")
    if title_node is not None:
        title = title_node.get_text(" ", strip=True)
    username_node = soup.select_one(".tgme_channel_info_header_username a")
    if username_node is not None:
        username = username_node.get_text(" ", strip=True).lstrip("@")
    if not username:
        parsed = urlparse(source_url)
        username = parsed.path.replace("/s/", "").strip("/")

    items: list[dict[str, Any]] = []
    for node in soup.select(".tgme_widget_message"):
        classes = set(node.get("class") or [])
        if "service_message" in classes:
            continue

        data_post = str(node.get("data-post") or "").strip()
        if "/" not in data_post:
            continue
        _, post_id = data_post.split("/", 1)
        post_id = post_id.strip()
        if not post_id:
            continue

        date_link = node.select_one(".tgme_widget_message_date")
        post_url = urljoin("https://t.me/", str(date_link.get("href") or "").strip()) if date_link else f"https://t.me/{username}/{post_id}"
        time_node = node.select_one(".tgme_widget_message_date time")
        published_at_utc = str(time_node.get("datetime") or "").strip() if time_node else ""

        text_raw = _message_text(node)
        if not text_raw:
            continue

        items.append(
            {
                "id": post_id,
                "post_id": post_id,
                "url": post_url,
                "post_url": post_url,
                "published_at_utc": published_at_utc,
                "date": published_at_utc,
                "title": _derive_title(text_raw, fallback=f"{title or username} #{post_id}"),
                "text": text_raw,
                "caption": text_raw,
                "media": _media_flag(node),
                "is_instruction": True,
                "is_recipe_candidate": False,
                "extracted_active_primary": "",
                "extracted_inci_primary": "",
                "parse_status": "imported_telegram_public_html",
                "source_channel_name": title or username,
                "source_channel_id": username,
            }
        )
    return title or username, username, items


def main() -> None:
    args = _args()
    channel = args.channel.strip().lstrip("@")
    base_url = (args.base_url or f"https://t.me/s/{channel}").strip()

    session = _session()
    seen_ids: set[str] = set()
    all_items: list[dict[str, Any]] = []
    resolved_title = channel
    resolved_username = channel
    before_token: str | None = None

    for _ in range(max(1, args.pages)):
        page_url = base_url if not before_token else f"{base_url}?before={before_token}"
        response = session.get(page_url, timeout=args.timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        title, username, items = _parse_page(soup, page_url)
        resolved_title = title or resolved_title
        resolved_username = username or resolved_username

        fresh_items = [item for item in items if item["id"] not in seen_ids]
        for item in fresh_items:
            seen_ids.add(item["id"])
        all_items.extend(fresh_items)

        next_before = _extract_before_token(soup, before_token)
        if not next_before:
            break
        before_token = next_before

    all_items.sort(key=lambda item: int(str(item.get("id") or "0")))

    generated_dir = ROOT / "generated" / "instruction_search" / f"telegram_export_{datetime.now().strftime('%Y-%m-%d')}"
    generated_dir.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output) if args.output else (generated_dir / "public_result.json")
    payload = {
        "platform": "telegram",
        "channel_name": resolved_title,
        "channel_id": resolved_username,
        "exported_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "items": all_items,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Fetched {len(all_items)} Telegram posts from @{resolved_username} into {output_path}")


if __name__ == "__main__":
    main()
