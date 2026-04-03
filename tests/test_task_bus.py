from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
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

    def test_heartbeat_and_retryable_fail_keep_task_claimable(self) -> None:
        with TemporaryDirectory() as tmp:
            settings = load_settings(tmp)
            ensure_runtime_layout(settings)
            bus = TaskBus(settings.runtime_root / "tasks")
            task = TaskEnvelope(
                task_id="case-2",
                source="telegram",
                command="ask",
                request="Нужен retry",
                chat_id="413513309",
                message_id=11,
                session_id="telegram-413513309",
                status="queued",
                max_attempts=2,
            )
            bus.enqueue(task)
            claimed = bus.claim_ready(worker_id="telegram-bot", lease_ttl_seconds=60)
            assert claimed is not None
            heartbeat = bus.heartbeat(claimed, worker_id="telegram-bot", lease_ttl_seconds=120)
            self.assertEqual(heartbeat.lease.worker_id, "telegram-bot")
            self.assertIsNotNone(heartbeat.lease.lease_expires_at)
            self.assertIsNotNone(heartbeat.lease.last_heartbeat_at)

            retried = bus.retry(heartbeat, error="temporary issue", delay_seconds=0)
            self.assertEqual(retried.status, "queued")
            self.assertIsNone(retried.lease)
            self.assertIsNotNone(retried.retry_not_before)
            self.assertEqual(retried.last_attempt_error, "temporary issue")

            claimed_again = bus.claim_ready(worker_id="telegram-bot", lease_ttl_seconds=60)
            assert claimed_again is not None
            self.assertEqual(claimed_again.attempt_count, 2)

            final = bus.retry(claimed_again, error="still broken", delay_seconds=0)
            self.assertEqual(final.status, "failed")

    def test_retry_not_before_blocks_immediate_reclaim(self) -> None:
        with TemporaryDirectory() as tmp:
            settings = load_settings(tmp)
            ensure_runtime_layout(settings)
            bus = TaskBus(settings.runtime_root / "tasks")
            task = TaskEnvelope(
                task_id="case-2b",
                source="telegram",
                command="ask",
                request="backoff",
                chat_id="413513309",
                message_id=13,
                session_id="telegram-413513309",
                status="queued",
                max_attempts=3,
            )
            bus.enqueue(task)
            claimed = bus.claim_ready(worker_id="telegram-bot", lease_ttl_seconds=60)
            assert claimed is not None
            retried = bus.retry(claimed, error="temporary issue", delay_seconds=60)
            self.assertEqual(retried.status, "queued")
            self.assertIsNotNone(retried.retry_not_before)
            claimed_again = bus.claim_ready(worker_id="telegram-bot", lease_ttl_seconds=60)
            self.assertIsNone(claimed_again)

    def test_expired_running_task_becomes_terminal_when_retry_budget_is_exhausted(self) -> None:
        with TemporaryDirectory() as tmp:
            settings = load_settings(tmp)
            ensure_runtime_layout(settings)
            bus = TaskBus(settings.runtime_root / "tasks")
            task = TaskEnvelope(
                task_id="case-3",
                source="telegram",
                command="ask",
                request="running task",
                chat_id="413513309",
                message_id=12,
                session_id="telegram-413513309",
                status="running",
                attempt_count=2,
                max_attempts=2,
            )
            task.lease = bus._build_lease(
                worker_id="telegram-bot",
                now=datetime.now(timezone.utc) - timedelta(seconds=600),
                ttl_seconds=1,
                attempt=2,
            )
            bus.enqueue(task)

            claimed = bus.claim_ready(worker_id="telegram-bot", lease_ttl_seconds=60)
            self.assertIsNone(claimed)
            stored = bus.load("case-3")
            assert stored is not None
            self.assertEqual(stored.status, "failed")


if __name__ == "__main__":
    unittest.main()
