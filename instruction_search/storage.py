from __future__ import annotations

import difflib
import json
from dataclasses import replace
from pathlib import Path

import aiosqlite

from .models import IndexedInstruction, SearchResult
from .normalize import compact_query, normalize_query, translit_query


DDL = """
CREATE TABLE IF NOT EXISTS instruction_index (
  instruction_id TEXT PRIMARY KEY,
  source_platform TEXT NOT NULL,
  source_channel_name TEXT NOT NULL,
  source_channel_id TEXT NOT NULL,
  source_post_id TEXT NOT NULL,
  post_url TEXT NOT NULL,
  published_at_utc TEXT NOT NULL,
  display_title TEXT NOT NULL,
  active_name TEXT NOT NULL,
  active_name_normalized TEXT NOT NULL,
  synonyms_json TEXT NOT NULL,
  inci_json TEXT NOT NULL,
  search_text TEXT NOT NULL,
  rank_weight INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active',
  text_excerpt TEXT NOT NULL DEFAULT '',
  parse_status TEXT NOT NULL DEFAULT 'indexed',
  tags_json TEXT NOT NULL DEFAULT '[]',
  updated_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_instruction_platform_status
  ON instruction_index(source_platform, status);
CREATE INDEX IF NOT EXISTS idx_instruction_active_name
  ON instruction_index(source_platform, active_name_normalized);
CREATE TABLE IF NOT EXISTS instruction_sync_state (
  state_key TEXT PRIMARY KEY,
  state_value TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);
"""


async def ensure_storage(db_path: str) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(DDL)
        await db.commit()


async def replace_platform_index(db_path: str, platform: str, rows: list[IndexedInstruction]) -> None:
    await ensure_storage(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM instruction_index WHERE source_platform=?", (platform,))
        await db.executemany(
            """
            INSERT INTO instruction_index(
              instruction_id, source_platform, source_channel_name, source_channel_id, source_post_id,
              post_url, published_at_utc, display_title, active_name, active_name_normalized,
              synonyms_json, inci_json, search_text, rank_weight, status, text_excerpt,
              parse_status, tags_json, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item.instruction_id,
                    item.source_platform,
                    item.source_channel_name,
                    item.source_channel_id,
                    item.source_post_id,
                    item.post_url,
                    item.published_at_utc,
                    item.display_title,
                    item.active_name,
                    item.active_name_normalized,
                    json.dumps(list(item.synonyms), ensure_ascii=False),
                    json.dumps(list(item.inci), ensure_ascii=False),
                    item.search_text,
                    item.rank_weight,
                    item.status,
                    item.text_excerpt,
                    item.parse_status,
                    item.tags_json,
                    item.updated_at_utc,
                )
                for item in rows
            ],
        )
        await db.commit()


async def set_sync_state(db_path: str, key: str, value: str, updated_at_utc: str) -> None:
    await ensure_storage(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO instruction_sync_state(state_key, state_value, updated_at_utc)
            VALUES(?, ?, ?)
            ON CONFLICT(state_key) DO UPDATE SET
              state_value=excluded.state_value,
              updated_at_utc=excluded.updated_at_utc
            """,
            (key, value, updated_at_utc),
        )
        await db.commit()


async def search(db_path: str, platform: str, query: str, limit: int = 3) -> list[SearchResult]:
    await ensure_storage(db_path)
    normalized = normalize_query(query)
    compact = compact_query(query)
    if not normalized:
        return []

    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            """
            SELECT instruction_id, display_title, active_name, post_url, text_excerpt, rank_weight,
                   active_name_normalized, synonyms_json, inci_json, search_text
            FROM instruction_index
            WHERE source_platform=? AND status='active'
            """,
            (platform,),
        ) as cur:
            rows = await cur.fetchall()

    exact_name: list[SearchResult] = []
    exact_alias: list[SearchResult] = []
    partial: list[SearchResult] = []
    fuzzy: list[SearchResult] = []
    for row in rows:
        synonyms = tuple(json.loads(row[7] or "[]"))
        inci = tuple(json.loads(row[8] or "[]"))
        search_text = row[9] or ""
        base = SearchResult(
            instruction_id=row[0],
            source_platform=platform,
            display_title=row[1],
            active_name=row[2],
            post_url=row[3],
            text_excerpt=row[4] or "",
            score=int(row[5] or 0),
            match_type="partial",
            synonyms=synonyms,
            inci=inci,
        )
        if normalized == (row[6] or ""):
            exact_name.append(replace(base, score=base.score + 300, match_type="exact_name"))
            continue
        if normalized in synonyms or normalized in inci:
            exact_alias.append(replace(base, score=base.score + 200, match_type="exact_alias"))
            continue
        if normalized in search_text:
            partial.append(replace(base, score=base.score + 100, match_type="partial"))
            continue

        candidates = [row[6] or "", *synonyms, *inci]
        best_ratio = 0.0
        query_forms = {compact, translit_query(query)}
        for candidate in candidates:
            if not candidate:
                continue
            candidate_forms = {compact_query(candidate), translit_query(candidate)}
            for query_form in query_forms:
                for candidate_form in candidate_forms:
                    if not query_form or not candidate_form:
                        continue
                    ratio = difflib.SequenceMatcher(None, query_form, candidate_form).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
        if best_ratio >= 0.72:
            fuzzy_bonus = int(best_ratio * 100)
            fuzzy.append(replace(base, score=base.score + fuzzy_bonus, match_type="fuzzy"))

    ranked = exact_name + exact_alias + partial
    if not ranked:
        ranked = fuzzy
    ranked.sort(key=lambda item: (-item.score, item.display_title))
    return ranked[:limit]
