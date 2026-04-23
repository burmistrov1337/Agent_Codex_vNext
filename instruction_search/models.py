from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class IndexedInstruction:
    instruction_id: str
    source_platform: str
    source_channel_name: str
    source_channel_id: str
    source_post_id: str
    post_url: str
    published_at_utc: str
    display_title: str
    active_name: str
    active_name_normalized: str
    synonyms: tuple[str, ...] = ()
    inci: tuple[str, ...] = ()
    search_text: str = ""
    rank_weight: int = 0
    status: str = "active"
    text_excerpt: str = ""
    parse_status: str = "indexed"
    tags_json: str = "[]"
    updated_at_utc: str = ""


@dataclass(frozen=True, slots=True)
class SearchResult:
    instruction_id: str
    source_platform: str
    display_title: str
    active_name: str
    post_url: str
    text_excerpt: str
    score: int
    match_type: str
    synonyms: tuple[str, ...] = field(default_factory=tuple)
    inci: tuple[str, ...] = field(default_factory=tuple)
