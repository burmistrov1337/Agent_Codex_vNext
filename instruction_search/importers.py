from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


_URL_RE = re.compile(r"https?://\S+")
_NON_LETTER_EDGE_RE = re.compile(r"^[^\wа-яА-Яa-zA-Z]+|[^\wа-яА-Яa-zA-Z]+$")
_TRAILING_STRENGTH_RE = re.compile(r"\s*(?:[-–—]?\s*\d+(?:[.,]\d+)?\s*%?)\s*$")
_INCI_RE = re.compile(r"\bINCI\s*[:\-]\s*([^\n]+)", re.IGNORECASE)
_UPPER_LATIN_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9-]{2,}\b")
_LATIN_TOKEN_ANYCASE_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9-]{2,}\b")
_ACTIVE_TOKEN_CONTEXT_RE = re.compile(
    r"(?:\bактив(?:а|ом)?\s+|(?:^|[^\w]))([A-Za-z][A-Za-z0-9-]{2,})\b",
    re.IGNORECASE,
)
_COSMETIC_ACTIVE_PREFIX_RE = re.compile(r"^\s*косметический\s+актив\s+", re.IGNORECASE)
_TITLE_GENERIC_PATTERNS = (
    "итак нам дано",
    "всем доброго дня",
    "всем отличного дня",
    "вы просили мы привезли",
    "сегодня рассказываем вам",
    "а пока вы изучаете",
)
_GENERIC_EXPORT_MARKERS = {
    "новинка",
    "рецепт",
    "канал готов",
    "канал создан",
    "сегодня",
    "вчера",
}


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _extract_urls(value: str) -> list[str]:
    return [match.group(0) for match in _URL_RE.finditer(value)]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _flatten_telegram_text(value: Any) -> tuple[str, list[str]]:
    if isinstance(value, str):
        return value, _extract_urls(value)
    if isinstance(value, dict):
        text, links = _flatten_telegram_text(value.get("text"))
        for candidate in (value.get("href"), value.get("url")):
            candidate = _stringify(candidate).strip()
            if candidate:
                links.append(candidate)
        return text, links
    if not isinstance(value, list):
        text = _stringify(value)
        return text, _extract_urls(text)

    parts: list[str] = []
    links: list[str] = []
    for item in value:
        text_part, text_links = _flatten_telegram_text(item)
        parts.append(text_part)
        links.extend(text_links)
    return "".join(parts), _unique(links)


def _derive_title(text_raw: str, fallback: str = "") -> str:
    for line in text_raw.splitlines():
        line = line.strip()
        if not line:
            continue
        alnum_count = sum(1 for char in line if char.isalnum())
        if alnum_count >= 4:
            return line[:180]
    return fallback[:180]


def _is_generic_export_line(line: str, channel_name: str = "") -> bool:
    normalized = re.sub(r"\s+", " ", line).strip().casefold()
    if not normalized:
        return True
    if channel_name and normalized == channel_name.casefold():
        return True
    if normalized in _GENERIC_EXPORT_MARKERS:
        return True
    if re.fullmatch(r"\d{1,2}\s+\S+(?:\s+\d{4})?", line.strip()):
        return True
    return False


def _clean_generic_export_text(text_raw: str, channel_name: str = "") -> tuple[str, str]:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text_raw.splitlines()]
    lines = [line for line in lines if line]

    while lines and _is_generic_export_line(lines[0], channel_name):
        lines.pop(0)

    clean_text = "\n".join(lines).strip()
    title = ""
    for line in lines:
        if _is_generic_export_line(line, channel_name):
            continue
        if len(line) >= 4:
            title = line[:180]
            break
    return clean_text, title


def _clean_active_candidate(candidate: str) -> str:
    candidate = candidate.strip()
    if not candidate:
        return ""
    candidate = _COSMETIC_ACTIVE_PREFIX_RE.sub("", candidate)
    candidate = _NON_LETTER_EDGE_RE.sub("", candidate)
    candidate = _TRAILING_STRENGTH_RE.sub("", candidate).strip()
    candidate = re.sub(r"\s+", " ", candidate)
    alpha_count = sum(1 for char in candidate if char.isalpha())
    if alpha_count < 4:
        return ""
    return candidate[:120]


def _derive_inci_primary(text_raw: str) -> str:
    match = _INCI_RE.search(text_raw)
    if not match:
        return ""
    value = match.group(1).strip()
    value = re.split(r"\band\b|,|/", value, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    return _clean_active_candidate(value)


def _looks_generic_title(title: str) -> bool:
    normalized = re.sub(r"\s+", " ", title.casefold()).strip()
    if normalized in _GENERIC_EXPORT_MARKERS:
        return True
    return any(pattern in normalized for pattern in _TITLE_GENERIC_PATTERNS)


def _prefer_latin_token(token: str) -> bool:
    token = token.strip()
    if len(token) < 3:
        return False
    letters = [char for char in token if char.isalpha()]
    if len(letters) < 3:
        return False
    return sum(1 for char in letters if char.isupper()) >= max(2, len(letters) - 1)


def _extract_text_active_candidate(title: str, text_raw: str) -> str:
    head = "\n".join(part.strip() for part in text_raw.splitlines()[:6] if part.strip())
    for source in (title, head, text_raw[:500]):
        if not source:
            continue
        active_context = _ACTIVE_TOKEN_CONTEXT_RE.search(source)
        if active_context:
            return active_context.group(1).upper()

        upper_match = _UPPER_LATIN_TOKEN_RE.search(source)
        if upper_match:
            return upper_match.group(0).upper()

        for match in _LATIN_TOKEN_ANYCASE_RE.finditer(source):
            token = match.group(0)
            if _prefer_latin_token(token):
                return token.upper()
    return ""


def _derive_active_primary(title: str, text_raw: str, inci_primary: str) -> str:
    title_candidate = _clean_active_candidate(title)
    extracted_text_token = _extract_text_active_candidate(title, text_raw)
    if extracted_text_token:
        title_token_match = _UPPER_LATIN_TOKEN_RE.search(title_candidate)
        if title_token_match and title_token_match.group(0).upper() == extracted_text_token:
            return extracted_text_token
    if title_candidate and not _looks_generic_title(title_candidate):
        return title_candidate
    if extracted_text_token:
        return extracted_text_token
    if inci_primary:
        return inci_primary
    latin_match = _UPPER_LATIN_TOKEN_RE.search(title) or _UPPER_LATIN_TOKEN_RE.search(text_raw[:400])
    if latin_match:
        return latin_match.group(0)
    return title_candidate


def _derive_telegram_url(
    message: dict[str, Any],
    exported_chat_id: str,
    provided_channel_id: str,
    text_links: list[str],
) -> str:
    direct_url = _stringify(message.get("url") or message.get("post_url") or message.get("link")).strip()
    if direct_url:
        return direct_url
    post_id = _stringify(message.get("id") or message.get("post_id")).strip()
    if not post_id:
        return text_links[0] if text_links else ""

    normalized_channel_id = provided_channel_id.strip()
    if normalized_channel_id.startswith("@"):
        return f"https://t.me/{normalized_channel_id.lstrip('@')}/{post_id}"
    if normalized_channel_id and normalized_channel_id.startswith("https://t.me/"):
        return f"{normalized_channel_id.rstrip('/')}/{post_id}"

    numeric_id = "".join(ch for ch in (provided_channel_id or exported_chat_id) if ch.isdigit())
    if numeric_id.startswith("100"):
        numeric_id = numeric_id[3:]
    if numeric_id:
        return f"https://t.me/c/{numeric_id}/{post_id}"
    return text_links[0] if text_links else ""


def _telegram_media_flag(message: dict[str, Any]) -> str:
    media_keys = (
        "photo",
        "thumbnail",
        "file",
        "video_file",
        "audio_file",
        "sticker_file",
        "animation_file",
        "mime_type",
        "media_type",
        "width",
        "height",
    )
    return "1" if any(message.get(key) for key in media_keys) else "0"


def _telegram_rows(payload: dict[str, Any], platform: str, channel_name: str, channel_id: str) -> list[list[Any]]:
    messages = payload.get("messages") or []
    exported_name = _stringify(payload.get("name")).strip()
    exported_chat_id = _stringify(payload.get("id")).strip()
    source_name = channel_name or exported_name
    source_id = channel_id or exported_chat_id

    rows: list[list[Any]] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        if _stringify(item.get("type")).strip().lower() == "service":
            continue

        text_raw, text_links = _flatten_telegram_text(item.get("text"))
        text_raw = text_raw.strip()
        if not text_raw:
            caption_raw, caption_links = _flatten_telegram_text(item.get("caption"))
            text_raw = caption_raw.strip()
            text_links = _unique(text_links + caption_links)

        title_fallback = _stringify(item.get("title")).strip()
        post_id = _stringify(item.get("id") or item.get("post_id")).strip()
        title = _derive_title(text_raw, fallback=title_fallback or f"{source_name or 'Telegram'} #{post_id}")
        inci_primary = _stringify(item.get("extracted_inci_primary")).strip() or _derive_inci_primary(text_raw)
        active_primary = _stringify(item.get("extracted_active_primary")).strip() or _derive_active_primary(title, text_raw, inci_primary)
        published_at = _stringify(item.get("published_at_utc") or item.get("date")).strip()
        tags = item.get("tags")
        if tags is None and text_links:
            tags = {"links": text_links}

        rows.append(
            [
                platform,
                source_name,
                source_id,
                post_id,
                _derive_telegram_url(item, exported_chat_id, channel_id, text_links),
                published_at,
                title,
                text_raw,
                _telegram_media_flag(item),
                "1" if item.get("is_instruction", True) else "0",
                "1" if item.get("is_recipe_candidate", False) else "0",
                active_primary,
                inci_primary,
                json.dumps(tags or [], ensure_ascii=False),
                _stringify(item.get("parse_status") or "imported_telegram_desktop").strip(),
                _stringify(item.get("last_synced_at_utc") or published_at).strip(),
            ]
        )
    return rows


def load_export_rows(input_path: str, platform: str, channel_name: str, channel_id: str) -> list[list[Any]]:
    path = Path(input_path)
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if platform == "telegram" and isinstance(payload, dict) and isinstance(payload.get("messages"), list):
        return _telegram_rows(payload, platform, channel_name, channel_id)

    items = payload if isinstance(payload, list) else payload.get("items") or payload.get("posts") or []
    rows: list[list[Any]] = []
    for item in items:
        text_raw = str(item.get("text") or item.get("caption") or "")
        cleaned_text, derived_title = _clean_generic_export_text(text_raw, channel_name)
        if cleaned_text:
            text_raw = cleaned_text
        raw_title = str(item.get("title") or item.get("caption") or item.get("text") or "").strip().splitlines()[0][:180]
        title = derived_title or raw_title
        inci_primary = str(item.get("extracted_inci_primary") or "").strip() or _derive_inci_primary(text_raw)
        active_primary = str(item.get("extracted_active_primary") or "").strip() or _derive_active_primary(title, text_raw, inci_primary)
        raw_post_id = str(item.get("id") or item.get("post_id") or "")
        post_id = raw_post_id
        if platform == "max":
            # Browser exports may contain short/repeated ids like "1", "2".
            # Build a deterministic unique id from payload so rows do not collapse in reindex.
            if (not raw_post_id) or len(raw_post_id) < 12:
                fingerprint = hashlib.sha1(f"{title}|{text_raw}".encode("utf-8", errors="ignore")).hexdigest()[:16]
                post_id = f"max-browser-{raw_post_id or 'x'}-{fingerprint}"

        rows.append(
            [
                platform,
                channel_name,
                channel_id,
                post_id,
                str(item.get("url") or item.get("post_url") or ""),
                str(item.get("published_at_utc") or item.get("date") or ""),
                title,
                text_raw,
                "1" if item.get("media") else "0",
                "1" if item.get("is_instruction", True) else "0",
                "1" if item.get("is_recipe_candidate", False) else "0",
                active_primary,
                inci_primary,
                json.dumps(item.get("tags") or [], ensure_ascii=False),
                str(item.get("parse_status") or "imported"),
                str(item.get("last_synced_at_utc") or item.get("published_at_utc") or ""),
            ]
        )
    return rows
