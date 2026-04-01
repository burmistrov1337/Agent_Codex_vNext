from __future__ import annotations

from datetime import datetime, timezone
import json
import re

from ..config import Settings
from ..contracts import MemoryIndexEntry


class MemoryStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.memory_root = settings.runtime_root / "memory"
        self.index_path = self.memory_root / "MEMORY.md"
        self.topics_root = self.memory_root / "topics"
        self.logs_root = self.memory_root / "logs"
        self.sessions_root = settings.runtime_root / "sessions"

    def remember(self, *, title: str, body: str, topic_slug: str | None = None):
        slug = topic_slug or self._slugify(title)
        topic_path = self.topics_root / f"{slug}.md"
        topic_path.parent.mkdir(parents=True, exist_ok=True)
        topic_path.write_text(f"# {title}\n\n{body.strip()}\n", encoding="utf-8")
        self._refresh_index()
        return topic_path

    def append_daily_log(self, title: str, body: str):
        now = datetime.now(timezone.utc)
        log_path = self.logs_root / now.strftime("%Y") / now.strftime("%m") / f"{now.strftime('%Y-%m-%d')}.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n## {title}\n\n{body.strip()}\n")
        return log_path

    def write_session_event(self, payload: dict):
        session_path = self.sessions_root / f"{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
        session_path.parent.mkdir(parents=True, exist_ok=True)
        with session_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return session_path

    def load_index(self) -> list[MemoryIndexEntry]:
        entries: list[MemoryIndexEntry] = []
        for topic_path in sorted(self.topics_root.glob("*.md")):
            title = topic_path.stem.replace("-", " ").strip().title()
            entries.append(
                MemoryIndexEntry(
                    title=title,
                    topic_path=str(topic_path.relative_to(self.memory_root)),
                    hook=f"Topic file for {title}",
                    last_updated=datetime.fromtimestamp(topic_path.stat().st_mtime, tz=timezone.utc).isoformat(),
                )
            )
        return entries

    def _refresh_index(self) -> None:
        entries = self.load_index()
        lines = ["# MEMORY", ""]
        for entry in entries:
            lines.append(f"- [{entry.title}]({entry.topic_path}) - {entry.hook}")
        self.index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _slugify(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9а-яА-Я_-]+", "-", value.strip().lower())
        normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
        return normalized or "memory-topic"
