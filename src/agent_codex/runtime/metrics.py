from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from ..config import Settings
from ..memory import MemoryStore


class RuntimeMetricsCollector:
    def __init__(self, settings: Settings, memory: MemoryStore) -> None:
        self.settings = settings
        self.memory = memory

    def collect(self) -> dict[str, Any]:
        task_counts = Counter()
        task_dir = self.settings.runtime_root / "tasks"
        for path in task_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                task_counts["broken"] += 1
                continue
            task_counts[str(payload.get("status") or "unknown")] += 1

        artifact_counts = Counter()
        artifacts_root = self.settings.runtime_root / "artifacts"
        for path in artifacts_root.rglob("*"):
            if not path.is_file():
                continue
            artifact_counts[path.suffix.lower() or "[no_ext]"] += 1

        return {
            "runtime_root": str(self.settings.runtime_root),
            "config_issue_count": len(self.settings.validate()),
            "backends": {
                "primary": self.settings.primary_reasoning_backend,
                "background": self.settings.background_backend,
                "cheap": self.settings.cheap_backend,
            },
            "backend_credentials": {
                "groq": bool(self.settings.groq_api_key),
                "openai": bool(self.settings.openai_api_key),
                "anthropic": bool(self.settings.anthropic_api_key),
                "ollama": bool(self.settings.ollama_base_url),
            },
            "memory": {
                "index_entries": len(self.memory.load_index()),
                "topic_files": self._count_files(self.memory.topics_root, "*.md"),
                "log_files": self._count_files(self.memory.logs_root, "*.md"),
                "session_files": self._count_files(self.memory.sessions_root, "*.jsonl"),
            },
            "tasks": {
                "dir": str(task_dir),
                "counts": dict(sorted(task_counts.items())),
            },
            "artifacts": {
                "root": str(artifacts_root),
                "counts_by_extension": dict(sorted(artifact_counts.items())),
            },
        }

    @staticmethod
    def _count_files(root: Path, pattern: str) -> int:
        if not root.exists():
            return 0
        return sum(1 for _ in root.rglob(pattern))
