from __future__ import annotations

import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_codex.config import ensure_runtime_layout, load_settings
from agent_codex.memory import ConsolidationEngine, ConsolidationPolicy, MemoryStore


class MemoryConsolidationTests(unittest.TestCase):
    def test_consolidation_deduplicates_notes_and_reports_stale_topics(self) -> None:
        with TemporaryDirectory() as tmp:
            settings = load_settings(tmp)
            ensure_runtime_layout(settings)
            store = MemoryStore(settings)
            store.append_daily_log("Run 1", "- Повторяемая заметка\n- Повторяемая заметка\n- Отдельный факт")
            store.append_daily_log("Run 2", "## Вывод\nПовторяемая заметка\nЕщё один факт")

            stale_topic = store.remember(title="Old Topic", body="Body", topic_slug="old-topic")
            old_ts = time.time() - 40 * 24 * 3600
            os.utime(stale_topic, (old_ts, old_ts))

            engine = ConsolidationEngine(
                settings,
                policy=ConsolidationPolicy(min_hours_between_runs=0, min_session_events=0, stale_topic_days=21),
            )
            result = engine.run()
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["stale_topics"], 1)

            topic_path = Path(result["topic_path"])
            body = topic_path.read_text(encoding="utf-8")
            self.assertIn("Повторяемая заметка.", body)
            self.assertEqual(body.count("Повторяемая заметка."), 1)
            self.assertIn("old topic", body.lower())


if __name__ == "__main__":
    unittest.main()
