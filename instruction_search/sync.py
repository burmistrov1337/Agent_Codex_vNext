from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any

from .importers import _derive_active_primary
from .models import IndexedInstruction
from .normalize import normalize_query, normalize_token_list
from .sheets import SheetsWorkbook
from .storage import replace_platform_index, set_sync_state


POSTS_TELEGRAM_SHEET = "POSTS_TELEGRAM"
POSTS_MAX_SHEET = "POSTS_MAX"
INSTRUCTION_INDEX_SHEET = "INSTRUCTION_INDEX"
SYNONYMS_SHEET = "SYNONYMS"
SYNC_STATE_SHEET = "SYNC_STATE"
RECIPE_BACKLOG_SHEET = "RECIPE_BACKLOG"
SHEET_NAMES = (
    POSTS_TELEGRAM_SHEET,
    POSTS_MAX_SHEET,
    INSTRUCTION_INDEX_SHEET,
    SYNONYMS_SHEET,
    SYNC_STATE_SHEET,
    RECIPE_BACKLOG_SHEET,
)

POST_HEADERS = [
    "source_platform",
    "source_channel_name",
    "source_channel_id",
    "source_post_id",
    "post_url",
    "published_at_utc",
    "title_raw",
    "text_raw",
    "media_flag",
    "is_instruction",
    "is_recipe_candidate",
    "extracted_active_primary",
    "extracted_inci_primary",
    "tags_json",
    "parse_status",
    "last_synced_at_utc",
]
INDEX_HEADERS = [
    "instruction_id",
    "source_platform",
    "source_channel_name",
    "source_channel_id",
    "source_post_id",
    "post_url",
    "published_at_utc",
    "display_title",
    "active_name",
    "active_name_normalized",
    "synonyms_json",
    "inci_json",
    "search_text",
    "rank_weight",
    "status",
    "text_excerpt",
    "parse_status",
    "tags_json",
    "updated_at_utc",
]
SYNONYM_HEADERS = [
    "canonical_active",
    "canonical_active_normalized",
    "synonym",
    "synonym_normalized",
    "inci",
    "inci_normalized",
    "language",
    "notes",
]
SYNC_STATE_HEADERS = ["state_key", "state_value", "updated_at_utc"]
RECIPE_HEADERS = POST_HEADERS

INSTRUCTION_INCLUDE_PATTERNS = tuple(
    normalize_query(value)
    for value in (
        "способ применения",
        "применение:",
        "применение ",
        "норма ввода",
        "норма ввода:",
        "процент ввода",
        "как использовать",
        "как применять",
        "добавить в",
        "добавьте в",
        "на 100 гр",
        "на 100г",
        "на 300 гр",
        "чайную ложку",
        "чайная ложка",
        "столовую ложку",
        "в шампунь",
        "в маску",
        "в бальзам",
        "в кондиционер",
        "в крем",
        "ввод в рецепт",
        "ввод:",
        "ввод ",
        "ввод 0",
        "inci name",
        "растворим",
        "растворимость",
        "используется в качестве",
    )
)
INSTRUCTION_EXCLUDE_PATTERNS = tuple(
    normalize_query(value)
    for value in (
        "акция",
        "скидк",
        "скидочные",
        "новинк",
        "в наличии",
        "поступил в наличии",
        "появился в наличии",
        "ловите активные ссылочки",
        "ссылки для быстрой покупки",
        "быстрой покупки",
        "wildberries",
        "wb ",
        " wb",
        "ozon",
        "ссылка на покупку",
        "ссылки на покупку",
        "активные ссылочки",
        "на сайте adk",
    )
)
COMPARISON_PATTERNS = tuple(
    normalize_query(value)
    for value in (
        "разница между",
        "сравним",
        "сравнение",
        "друг и конкурент",
        "чем отличается",
        "конкурент",
    )
)
RECIPE_PATTERNS = tuple(
    normalize_query(value)
    for value in (
        "рецепт",
        "формула",
        "собрали для вас формулу",
        "сочетани",
        "в масках",
        "в кондиционерах",
        "энзимного пилинга",
        "шампунь для",
    )
)


@dataclass(frozen=True, slots=True)
class SynonymEntry:
    canonical_active: str
    canonical_active_normalized: str
    synonym: str
    synonym_normalized: str
    inci: str
    inci_normalized: str


def _now_utc() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def bootstrap_instruction_workbook(workbook: SheetsWorkbook) -> None:
    workbook.ensure_sheets(
        {
            POSTS_TELEGRAM_SHEET: POST_HEADERS,
            POSTS_MAX_SHEET: POST_HEADERS,
            INSTRUCTION_INDEX_SHEET: INDEX_HEADERS,
            SYNONYMS_SHEET: SYNONYM_HEADERS,
            SYNC_STATE_SHEET: SYNC_STATE_HEADERS,
            RECIPE_BACKLOG_SHEET: RECIPE_HEADERS,
        }
    )


def _rows_to_dicts(rows: list[list[str]]) -> list[dict[str, str]]:
    if not rows:
        return []
    headers = rows[0]
    result: list[dict[str, str]] = []
    for row in rows[1:]:
        normalized_row = [row[idx] if idx < len(row) else "" for idx in range(len(headers))]
        if normalized_row == headers:
            continue
        result.append({headers[idx]: normalized_row[idx] for idx in range(len(headers))})
    return result


def _load_synonyms(workbook: SheetsWorkbook) -> list[SynonymEntry]:
    rows = _rows_to_dicts(workbook.read_rows(SYNONYMS_SHEET))
    items: list[SynonymEntry] = []
    for row in rows:
        items.append(
            SynonymEntry(
                canonical_active=row.get("canonical_active", ""),
                canonical_active_normalized=normalize_query(row.get("canonical_active_normalized") or row.get("canonical_active", "")),
                synonym=row.get("synonym", ""),
                synonym_normalized=normalize_query(row.get("synonym_normalized") or row.get("synonym", "")),
                inci=row.get("inci", ""),
                inci_normalized=normalize_query(row.get("inci_normalized") or row.get("inci", "")),
            )
        )
    return items


def _sheet_for_platform(platform: str) -> str:
    return POSTS_TELEGRAM_SHEET if platform == "telegram" else POSTS_MAX_SHEET


def _infer_synonyms(active_name: str, inci_value: str, synonyms: list[SynonymEntry]) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    active_normalized = normalize_query(active_name)
    matched_synonyms: list[str] = []
    matched_inci: list[str] = []
    canonical_name = active_name
    for item in synonyms:
        if active_normalized and active_normalized in {
            item.canonical_active_normalized,
            item.synonym_normalized,
            item.inci_normalized,
        }:
            canonical_name = item.canonical_active or canonical_name
            matched_synonyms.extend([value for value in [item.synonym, item.canonical_active] if value])
            if item.inci:
                matched_inci.append(item.inci)
        if inci_value and normalize_query(inci_value) == item.inci_normalized:
            canonical_name = item.canonical_active or canonical_name
            matched_synonyms.extend([value for value in [item.synonym, item.canonical_active] if value])
            if item.inci:
                matched_inci.append(item.inci)
    if inci_value:
        matched_inci.append(inci_value)
    matched_synonyms.extend([active_name, canonical_name])
    return normalize_token_list(matched_synonyms), normalize_token_list(matched_inci), canonical_name


def _should_redrive_active(value: str) -> bool:
    candidate = (value or "").strip()
    if not candidate:
        return True
    if len(candidate) > 40:
        return True
    normalized = normalize_query(candidate)
    if " " in candidate and len(candidate.split()) >= 4:
        return True
    if any(marker in normalized for marker in ("механизм действия", "итак нам дано", "доброе утро", "сегодня")):
        return True
    return False


def _rank_instruction(active_normalized: str, title: str, content_normalized: str) -> int:
    rank_weight = 100
    title_normalized = normalize_query(title)
    if active_normalized and title_normalized.startswith(active_normalized):
        rank_weight += 80
    if active_normalized and f"{active_normalized} " in title_normalized:
        rank_weight += 40
    if any(pattern in content_normalized for pattern in COMPARISON_PATTERNS):
        rank_weight -= 50
    if any(pattern in content_normalized for pattern in RECIPE_PATTERNS):
        rank_weight -= 40
    if "норма ввода" in content_normalized:
        rank_weight += 30
    if "способ применения" in content_normalized or "применение" in content_normalized:
        rank_weight += 20
    if "на 100 гр" in content_normalized or "на 100г" in content_normalized:
        rank_weight += 20
    return rank_weight


def _display_title_for_row(title: str, active_name: str, channel_name: str) -> str:
    raw_title = (title or "").strip()
    raw_active = (active_name or "").strip()
    raw_channel = (channel_name or "").strip()
    if not raw_title:
        return raw_active
    normalized_title = normalize_query(raw_title)
    normalized_channel = normalize_query(raw_channel)
    if normalized_channel and normalized_title == normalized_channel:
        return raw_active or raw_title
    if raw_title in {"Новинка", "Рецепт", "Канал готов", "Канал создан"}:
        return raw_active or raw_title
    if re.fullmatch(r"\d{1,2}\s+\S+(?:\s+\d{4})?", raw_title):
        return raw_active or raw_title
    return raw_title


def _build_index_entries(platform: str, posts: list[dict[str, str]], synonyms: list[SynonymEntry]) -> tuple[list[IndexedInstruction], list[list[Any]]]:
    indexed: list[IndexedInstruction] = []
    recipe_rows: list[list[Any]] = []
    seen_instruction_ids: set[str] = set()
    for row in posts:
        if normalize_query(row.get("is_recipe_candidate", "")) in {"1", "true", "yes"}:
            recipe_rows.append([row.get(header, "") for header in RECIPE_HEADERS])
            continue
        if normalize_query(row.get("is_instruction", "")) not in {"1", "true", "yes"}:
            continue
        active_primary = row.get("extracted_active_primary", "").strip()
        title = row.get("title_raw", "").strip() or active_primary
        text_raw = row.get("text_raw", "").strip()
        if platform == "max":
            max_title_prefix = "косметический актив "
            title_norm = normalize_query(title)
            if title_norm.startswith(max_title_prefix):
                # MAX-specific deterministic rule from product requirements:
                # "Косметический актив <название>" -> canonical active is <название>.
                suffix = title[len("Косметический актив") :].strip(" :-—–\t")
                if suffix:
                    active_primary = suffix
        if _should_redrive_active(active_primary):
            active_primary = _derive_active_primary(title, text_raw, row.get("extracted_inci_primary", "").strip())
        content_normalized = normalize_query(f"{title}\n{text_raw}")
        if not active_primary and not title:
            continue
        has_include_signal = any(pattern in content_normalized for pattern in INSTRUCTION_INCLUDE_PATTERNS)
        # Fallback: keep known actives searchable even when source text encoding/style
        # does not contain our formal "instruction" phrases.
        if not has_include_signal:
            if any(marker in content_normalized for marker in ("badd", "bis aminopropyl", "dimaleate")):
                has_include_signal = True
        has_exclude_signal = any(pattern in content_normalized for pattern in INSTRUCTION_EXCLUDE_PATTERNS)
        if has_exclude_signal and not has_include_signal:
            continue
        if not has_include_signal:
            continue
        normalized_synonyms, normalized_inci, canonical_name = _infer_synonyms(
            active_primary or title,
            row.get("extracted_inci_primary", ""),
            synonyms,
        )
        active_name = canonical_name or active_primary or title
        active_normalized = normalize_query(active_name)
        # Keep a short snippet for bot output, but index a longer body window
        # so actives mentioned deeper in long posts remain searchable.
        text_excerpt = text_raw[:420]
        search_body = normalize_query(text_raw[:4000])
        search_text = " ".join(
            filter(
                None,
                [
                    active_normalized,
                    " ".join(normalized_synonyms),
                    " ".join(normalized_inci),
                    normalize_query(title),
                    search_body,
                ],
            )
        )
        rank_weight = _rank_instruction(active_normalized, title, content_normalized)
        post_id = row.get("source_post_id", "")
        instruction_id = f"{platform}:{post_id or active_normalized}"
        if instruction_id in seen_instruction_ids:
            continue
        seen_instruction_ids.add(instruction_id)
        display_title = _display_title_for_row(title, active_name, row.get("source_channel_name", ""))
        indexed.append(
            IndexedInstruction(
                instruction_id=instruction_id,
                source_platform=platform,
                source_channel_name=row.get("source_channel_name", ""),
                source_channel_id=row.get("source_channel_id", ""),
                source_post_id=post_id,
                post_url=row.get("post_url", ""),
                published_at_utc=row.get("published_at_utc", ""),
                display_title=display_title or active_name,
                active_name=active_name,
                active_name_normalized=active_normalized,
                synonyms=normalized_synonyms,
                inci=normalized_inci,
                search_text=search_text,
                rank_weight=rank_weight,
                status="active",
                text_excerpt=text_excerpt,
                parse_status=row.get("parse_status", "") or "indexed",
                tags_json=row.get("tags_json", "") or "[]",
                updated_at_utc=_now_utc(),
            )
        )
    return indexed, recipe_rows


async def rebuild_platform_index(
    workbook: SheetsWorkbook,
    *,
    platform: str,
    sqlite_db_path: str,
) -> int:
    bootstrap_instruction_workbook(workbook)
    synonyms = _load_synonyms(workbook)
    posts = _rows_to_dicts(workbook.read_rows(_sheet_for_platform(platform)))
    indexed, recipe_rows = _build_index_entries(platform, posts, synonyms)

    all_index_rows = _rows_to_dicts(workbook.read_rows(INSTRUCTION_INDEX_SHEET))
    kept_other_rows = [row for row in all_index_rows if row.get("source_platform") != platform]
    merged_rows = kept_other_rows + [
        {
            "instruction_id": item.instruction_id,
            "source_platform": item.source_platform,
            "source_channel_name": item.source_channel_name,
            "source_channel_id": item.source_channel_id,
            "source_post_id": item.source_post_id,
            "post_url": item.post_url,
            "published_at_utc": item.published_at_utc,
            "display_title": item.display_title,
            "active_name": item.active_name,
            "active_name_normalized": item.active_name_normalized,
            "synonyms_json": json.dumps(list(item.synonyms), ensure_ascii=False),
            "inci_json": json.dumps(list(item.inci), ensure_ascii=False),
            "search_text": item.search_text,
            "rank_weight": str(item.rank_weight),
            "status": item.status,
            "text_excerpt": item.text_excerpt,
            "parse_status": item.parse_status,
            "tags_json": item.tags_json,
            "updated_at_utc": item.updated_at_utc,
        }
        for item in indexed
    ]
    workbook.rewrite_sheet(
        INSTRUCTION_INDEX_SHEET,
        INDEX_HEADERS,
        [[row.get(header, "") for header in INDEX_HEADERS] for row in merged_rows],
    )
    all_recipe_rows = _rows_to_dicts(workbook.read_rows(RECIPE_BACKLOG_SHEET))
    kept_other_recipe_rows = [row for row in all_recipe_rows if row.get("source_platform") != platform]
    merged_recipe_rows = kept_other_recipe_rows + [
        {header: recipe_row[idx] if idx < len(recipe_row) else "" for idx, header in enumerate(RECIPE_HEADERS)}
        for recipe_row in recipe_rows
    ]
    workbook.rewrite_sheet(
        RECIPE_BACKLOG_SHEET,
        RECIPE_HEADERS,
        [[row.get(header, "") for header in RECIPE_HEADERS] for row in merged_recipe_rows],
    )
    existing_sync_rows = _rows_to_dicts(workbook.read_rows(SYNC_STATE_SHEET))
    kept_sync_rows = [row for row in existing_sync_rows if row.get("state_key") != f"last_rebuild_{platform}"]
    now = _now_utc()
    workbook.rewrite_sheet(
        SYNC_STATE_SHEET,
        SYNC_STATE_HEADERS,
        [[row.get(header, "") for header in SYNC_STATE_HEADERS] for row in kept_sync_rows]
        + [[f"last_rebuild_{platform}", str(len(indexed)), now]],
    )
    await replace_platform_index(sqlite_db_path, platform, indexed)
    await set_sync_state(sqlite_db_path, f"last_rebuild_{platform}", str(len(indexed)), now)
    return len(indexed)
