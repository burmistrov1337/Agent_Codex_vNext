from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_codex.config import ensure_runtime_layout, load_settings
from agent_codex.contracts import TaskEnvelope
from agent_codex.runtime.task_bus import TaskBus


class TaskBusTests(unittest.TestCase):
    def test_claim_complete_and_persist_result_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            settings = load_settings(tmp)
            ensure_runtime_layout(settings)
            bus = TaskBus(settings.runtime_root / "tasks")
            task = TaskEnvelope(
                task_id="case-1",
                source="telegram",
                command="ask",
                request="Подготовь краткую сводку",
                chat_id="413513309",
                message_id=10,
                session_id="telegram-413513309",
                status="queued",
            )
            bus.enqueue(task)

            claimed = bus.claim_ready(worker_id="telegram-bot")
            self.assertIsNotNone(claimed)
            assert claimed is not None
            self.assertEqual(claimed.status, "leased")
            self.assertEqual(claimed.attempt_count, 1)
            self.assertIsNotNone(claimed.lease)

            bus.mark_running(claimed, run_id="run-1")
            running = bus.load("case-1")
            assert running is not None
            self.assertEqual(running.status, "running")
            self.assertEqual(running.run_id, "run-1")

            bus.complete(
                running,
                run_id="run-1",
                result_envelope_path=str(Path(tmp) / "run_envelope.json"),
                result_summary="Задача завершена.",
                artifact_paths=[str(Path(tmp) / "summary.md")],
            )
            completed = bus.load("case-1")
            assert completed is not None
            self.assertEqual(completed.status, "completed")
            self.assertEqual(completed.attempt_count, 1)
            self.assertIsNone(completed.lease)
            self.assertTrue(completed.result_envelope_path.endswith("run_envelope.json"))

    def test_list_tasks_filters_by_status(self) -> None:
        with TemporaryDirectory() as tmp:
            settings = load_settings(tmp)
            ensure_runtime_layout(settings)
            bus = TaskBus(settings.runtime_root / "tasks")
            for task_id, status in [("a", "queued"), ("b", "cancelled"), ("c", "completed")]:
                bus.enqueue(
                    TaskEnvelope(
                        task_id=task_id,
                        source="telegram",
                        command="ask",
                        request=task_id,
                        chat_id="1",
                        message_id=1,
                        session_id="s",
                        status=status,
                    )
                )
            queued = bus.list_tasks(statuses={"queued"})
            self.assertEqual([item.task_id for item in queued], ["a"])


if __name__ == "__main__":
    unittest.main()
