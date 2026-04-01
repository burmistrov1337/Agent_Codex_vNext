from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json

from ..config import Settings
from .store import MemoryStore


@dataclass(slots=True)
class ConsolidationPolicy:
    min_hours_between_runs: int = 24
    min_session_events: int = 5


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
            recent_logs = sorted(self.store.logs_root.rglob("*.md"))[-7:]
            combined = []
            for path in recent_logs:
                text = path.read_text(encoding="utf-8", errors="replace").strip()
                if text:
                    combined.append(f"## {path.name}\n\n{text}")
            body = "\n\n".join(combined) or "No recent logs."
            topic_path = self.store.remember(
                title="Recent Consolidated Learnings",
                body=body,
                topic_slug="recent-consolidated-learnings",
            )
            state = self._read_state()
            state["last_run_at"] = datetime.now(timezone.utc).isoformat()
            state["session_events_since_last_run"] = 0
            self._write_state(state)
            return {"status": "completed", "topic_path": str(topic_path)}
        finally:
            if self.lock_path.exists():
                self.lock_path.unlink()

    def _read_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write_state(self, payload: dict) -> None:
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
