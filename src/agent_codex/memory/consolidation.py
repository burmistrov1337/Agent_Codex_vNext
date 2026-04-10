from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import re

from ..config import Settings
from .store import MemoryStore


@dataclass(slots=True)
class ConsolidationPolicy:
    min_hours_between_runs: int = 24
    min_session_events: int = 5
    max_recent_logs: int = 10
    stale_topic_days: int = 21


class ConsolidationEngine:
    def __init__(self, settings: Settings, policy: ConsolidationPolicy | None = None) -> None:
        self.settings = settings
        self.policy = policy or ConsolidationPolicy()
        self.state_path = settings.runtime_root / "memory" / ".consolidation_state.json"
        self.lock_path = settings.runtime_root / "memory" / ".consolidation.lock"
        self.store = MemoryStore(settings)

    def should_run(self) -> tuple[bool, str]:
        if self.lock_path.exists():
            return False, "consolidation lock is active"
        state = self._read_state()
        last_run_raw = state.get("last_run_at")
        if last_run_raw:
            last_run = datetime.fromisoformat(last_run_raw)
            if datetime.now(timezone.utc) - last_run < timedelta(hours=self.policy.min_hours_between_runs):
                return False, "time gate is not satisfied"
        session_events = state.get("session_events_since_last_run", 0)
        if session_events < self.policy.min_session_events:
            return False, "session gate is not satisfied"
        return True, "ready"

    def record_session_event(self) -> None:
        state = self._read_state()
        state["session_events_since_last_run"] = int(state.get("session_events_since_last_run", 0)) + 1
        self._write_state(state)

    def run(self) -> dict[str, str | int]:
        allowed, reason = self.should_run()
        if not allowed:
            return {"status": "skipped", "reason": reason}
        self.lock_path.write_text("locked\n", encoding="utf-8")
        try:
            recent_logs = sorted(self.store.logs_root.rglob("*.md"))[-self.policy.max_recent_logs :]
            note_candidates: list[str] = []
            log_names: list[str] = []
            for path in recent_logs:
                text = path.read_text(encoding="utf-8", errors="replace").strip()
                if text:
                    log_names.append(path.name)
                    note_candidates.extend(self._extract_notes(text))
            stale_topics = self._find_stale_topics()
            unique_notes = list(dict.fromkeys(note_candidates))

            body_parts = ["## Key learnings", ""]
            if unique_notes:
                body_parts.extend(f"- {item}" for item in unique_notes[:12])
            else:
                body_parts.append("- No strong repeated learnings were extracted from recent logs.")

            body_parts.extend(["", "## Sources", ""])
            body_parts.extend(f"- {name}" for name in log_names or ["No recent logs."])

            if stale_topics:
                body_parts.extend(["", "## Stale topics to review", ""])
                body_parts.extend(f"- {item}" for item in stale_topics[:10])

            body = "\n".join(body_parts)
            topic_path = self.store.remember(
                title="Recent Consolidated Learnings",
                body=body,
                topic_slug="recent-consolidated-learnings",
            )
            state = self._read_state()
            state["last_run_at"] = datetime.now(timezone.utc).isoformat()
            state["session_events_since_last_run"] = 0
            self._write_state(state)
            return {
                "status": "completed",
                "topic_path": str(topic_path),
                "source_logs": len(log_names),
                "unique_notes": len(unique_notes),
                "stale_topics": len(stale_topics),
            }
        finally:
            if self.lock_path.exists():
                self.lock_path.unlink()

    def _read_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write_state(self, payload: dict) -> None:
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _find_stale_topics(self) -> list[str]:
        threshold = datetime.now(timezone.utc) - timedelta(days=self.policy.stale_topic_days)
        stale: list[str] = []
        for path in self.store.topics_root.glob("*.md"):
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if modified < threshold and path.stem != "recent-consolidated-learnings":
                stale.append(path.stem.replace("-", " "))
        return sorted(stale)

    @staticmethod
    def _extract_notes(text: str) -> list[str]:
        notes: list[str] = []
        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", raw_line.strip())
            if not line:
                continue
            if line.startswith("#"):
                line = line.lstrip("#").strip()
            elif line.startswith("-"):
                line = line[1:].strip()
            elif line.startswith("*"):
                line = line[1:].strip()
            else:
                line = line[:160]
            if len(line) < 12:
                continue
            notes.append(line.rstrip(".") + ".")
        return notes
