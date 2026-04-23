from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export MAX channel posts from an already opened isolated Yandex Browser profile via Playwright CDP."
    )
    parser.add_argument("--url", required=True, help="MAX web route, for example https://web.max.ru/-72158373787757")
    parser.add_argument("--output", help="Optional JSON output path.")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9223", help="CDP endpoint from start_max_browser_profile.ps1.")
    parser.add_argument("--channel-name", default="", help="Channel name override for export metadata.")
    parser.add_argument("--channel-id", default="", help="Channel id override for export metadata.")
    parser.add_argument("--wait-ms", type=int, default=15000, help="How long to wait for page rendering.")
    parser.add_argument("--scrolls", type=int, default=8, help="How many history scroll passes to do before export.")
    parser.add_argument("--scroll-pause-ms", type=int, default=1500, help="Pause between history scroll passes.")
    parser.add_argument("--max-items", type=int, default=250, help="Hard cap for exported message blocks.")
    return parser.parse_args()


def _build_output_path(output_arg: str | None) -> Path:
    if output_arg:
        return Path(output_arg)
    generated_dir = ROOT / "generated" / "instruction_search" / f"max_export_{datetime.now().strftime('%Y-%m-%d')}"
    generated_dir.mkdir(parents=True, exist_ok=True)
    return generated_dir / "browser_result.json"


def _normalize_item(raw: dict[str, Any], fallback_channel_name: str, fallback_channel_id: str) -> dict[str, Any]:
    text = str(raw.get("text") or "").strip()
    message_id = str(raw.get("id") or "").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    while lines and lines[0] in {fallback_channel_name, "Сегодня", "Вчера"}:
        lines.pop(0)
    while lines and lines[0] in {"Новинка", "Рецепт"}:
        lines.pop(0)

    title = ""
    for line in lines:
        if len(line) >= 4:
            title = line[:180]
            break
    if title in {"Канал готов", "Канал создан"}:
        title = ""
    if not title:
        title = (fallback_channel_name or "MAX post")[:180]

    clean_text = "\n".join(lines) if lines else text
    return {
        "id": message_id,
        "post_id": message_id,
        "url": str(raw.get("post_url") or "").strip(),
        "post_url": str(raw.get("post_url") or "").strip(),
        "published_at_utc": "",
        "date": "",
        "title": title,
        "text": clean_text,
        "caption": clean_text,
        "media": bool(raw.get("has_media")),
        "is_instruction": True,
        "is_recipe_candidate": False,
        "extracted_active_primary": "",
        "extracted_inci_primary": "",
        "parse_status": "imported_max_browser",
        "source_channel_name": fallback_channel_name,
        "source_channel_id": fallback_channel_id,
    }


def _page_script() -> str:
    return """
() => {
  const seen = new Set();
  const results = [];
  const candidates = Array.from(document.querySelectorAll('.history .item'));

  for (const node of candidates) {
    const text = (node.innerText || '').replace(/\\u00a0/g, ' ').trim();
    if (!text || text.length < 24) continue;
    if (text === 'Пост') continue;

    const id = node.getAttribute('data-message-id')
      || node.getAttribute('data-id')
      || node.getAttribute('data-index')
      || text.slice(0, 80);
    if (seen.has(id)) continue;
    seen.add(id);

    const mediaNode = node.querySelector('img, video, [style*="background-image"]');
    const links = Array.from(node.querySelectorAll('a[href]'))
      .map((a) => String(a.getAttribute('href') || '').trim())
      .filter(Boolean);

    let postUrl = '';
    const postUrlPattern = new RegExp('^https?://(?:www\\\\.)?max\\\\.ru/id[^/]+/[A-Za-z0-9_-]+', 'i');
    for (const href of links) {
      const absolute = href.startsWith('http')
        ? href
        : new URL(href, window.location.origin).href;
      if (postUrlPattern.test(absolute)) {
        postUrl = absolute;
        break;
      }
    }

    results.push({
      id: String(id).trim(),
      text,
      has_media: !!mediaNode,
      post_url: postUrl,
    });
  }

  return {
    title: document.title || '',
    items: results,
    url: window.location.href,
  };
}
"""


def _pick_page(browser) -> Any:
    for context in browser.contexts:
        for page in context.pages:
            if "web.max.ru" in page.url:
                return context, page
    if browser.contexts:
        context = browser.contexts[0]
        return context, (context.pages[0] if context.pages else context.new_page())
    context = browser.new_context()
    return context, context.new_page()


def main() -> int:
    args = _args()
    output_path = _build_output_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(args.cdp_url)
        try:
            context, page = _pick_page(browser)
            page.goto(args.url, wait_until="domcontentloaded")
            page.wait_for_timeout(max(args.wait_ms, 1000))

            for _ in range(max(args.scrolls, 0)):
                page.evaluate(
                    """
() => {
  const scroller = document.querySelector('.history .scrollable');
  if (scroller) {
    scroller.scrollTop = 0;
  }
}
"""
                )
                page.mouse.wheel(0, -5000)
                page.wait_for_timeout(max(args.scroll_pause_ms, 250))

            try:
                page.wait_for_load_state("networkidle", timeout=max(args.wait_ms, 1000))
            except PlaywrightTimeoutError:
                pass

            extracted = page.evaluate(_page_script())
            channel_name = args.channel_name.strip() or str(extracted.get("title") or "MAX browser export").strip()
            channel_id = args.channel_id.strip() or args.url
            source_url = str(extracted.get("url") or args.url)
            items = extracted.get("items") or []
            normalized = [
                _normalize_item(item, channel_name, channel_id)
                for item in items[: max(args.max_items, 1)]
            ]

            payload = {
                "platform": "max",
                "channel_name": channel_name,
                "channel_id": channel_id,
                "exported_at_utc": datetime.now(tz=timezone.utc).isoformat(),
                "source_url": source_url,
                "items": normalized,
            }
            output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Exported {len(normalized)} MAX posts from browser into {output_path}")
            return 0
        finally:
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
