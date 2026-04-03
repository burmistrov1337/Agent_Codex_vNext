from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from ..contracts import TaskEnvelope
from .task_bus import TaskBus


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


@dataclass(slots=True)
class MaintenanceSweepResult:
    total_tasks: int = 0
    ready_queued: int = 0
    active_leases: int = 0
    reclaimed_to_queue: int = 0
    terminal_failures: int = 0
    awaiting_confirmation: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class TaskBusMaintainer:
    def __init__(self, task_bus: TaskBus, *, reclaim_delay_seconds: int = 5) -> None:
        self.task_bus = task_bus
        self.reclaim_delay_seconds = reclaim_delay_seconds

    def sweep_once(self) -> MaintenanceSweepResult:
        now = datetime.now(timezone.utc)
        result = MaintenanceSweepResult()
        for task in self.task_bus.list_tasks():
            result.total_tasks += 1
            if task.status == "awaiting_confirmation":
                result.awaiting_confirmation += 1
                continue
            if task.status == "queued":
                retry_at = _parse_iso(task.retry_not_before)
                if retry_at is None or retry_at <= now:
                    result.ready_queued += 1
                continue
            if task.status in {"leased", "running"} and task.lease:
                if self._lease_expired(task, now=now):
                    error = task.last_attempt_error or task.error or "Lease expired before worker completion"
                    if self.task_bus.can_retry(task):
                        self.task_bus.retry(task, error=error, delay_seconds=self.reclaim_delay_seconds)
                        result.reclaimed_to_queue += 1
                    else:
                        self.task_bus.fail(task, error=error)
                        result.terminal_failures += 1
                    continue
                result.active_leases += 1
        return result

    def run(self, *, once: bool = False, max_cycles: int | None = None, sleep_seconds: int = 5) -> dict:
        cycles = 0
        last_sweep = MaintenanceSweepResult()
        while True:
            last_sweep = self.sweep_once()
            cycles += 1
            if once:
                break
            if max_cycles is not None and cycles >= max_cycles:
                break
            time.sleep(max(sleep_seconds, 1))
        return {
            "cycles": cycles,
            "last_sweep": last_sweep.to_dict(),
        }

    def _lease_expired(self, task: TaskEnvelope, *, now: datetime) -> bool:
        if task.lease is None:
            return False
        expires_at = _parse_iso(task.lease.lease_expires_at)
        if expires_at is None:
            return True
        return expires_at <= now


class TaskHeartbeat:
    def __init__(
        self,
        task_bus: TaskBus,
        task: TaskEnvelope,
        *,
        worker_id: str,
        interval_seconds: int = 30,
        lease_ttl_seconds: int = 300,
    ) -> None:
        self.task_bus = task_bus
        self.task = task
        self.worker_id = worker_id
        self.interval_seconds = max(interval_seconds, 1)
        self.lease_ttl_seconds = max(lease_ttl_seconds, self.interval_seconds + 1)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "TaskHeartbeat":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name=f"task-heartbeat-{self.task.task_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_seconds + 2)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.task = self.task_bus.heartbeat(
                    self.task,
                    worker_id=self.worker_id,
                    lease_ttl_seconds=self.lease_ttl_seconds,
                )
            except Exception:
                return
