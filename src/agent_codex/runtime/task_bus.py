from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..contracts import ConfirmationRequest, TaskEnvelope, TaskLease, TelegramAttachment, utc_now_iso


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


class TaskBus:
    def __init__(self, tasks_root: Path, *, prefix: str = "telegram_") -> None:
        self.tasks_root = tasks_root
        self.prefix = prefix
        self.tasks_root.mkdir(parents=True, exist_ok=True)

    def enqueue(self, task: TaskEnvelope) -> TaskEnvelope:
        self.save(task)
        return task

    def save(self, task: TaskEnvelope) -> None:
        self.path_for(task.task_id).write_text(
            json.dumps(asdict(task), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, task_id: str) -> TaskEnvelope | None:
        path = self.path_for(task_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        attachments = [TelegramAttachment(**item) for item in data.get("attachments", [])]
        confirmation_payload = data.get("confirmation_request")
        confirmation = ConfirmationRequest(**confirmation_payload) if confirmation_payload else None
        lease_payload = data.get("lease")
        lease = TaskLease(**lease_payload) if lease_payload else None
        return TaskEnvelope(
            task_id=data["task_id"],
            source=data["source"],
            command=data["command"],
            request=data["request"],
            chat_id=data["chat_id"],
            message_id=int(data["message_id"]),
            session_id=data["session_id"],
            status=data["status"],
            attachments=attachments,
            risky=bool(data.get("risky")),
            confirmation_request=confirmation,
            attempt_count=int(data.get("attempt_count", 0)),
            max_attempts=int(data.get("max_attempts", 3)),
            lease=lease,
            run_id=data.get("run_id"),
            result_envelope_path=data.get("result_envelope_path"),
            result_summary=data.get("result_summary"),
            artifact_paths=list(data.get("artifact_paths") or []),
            retry_not_before=data.get("retry_not_before"),
            last_attempt_error=data.get("last_attempt_error"),
            last_error=data.get("last_error"),
            error=data.get("error"),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    def list_tasks(self, *, chat_id: str | None = None, statuses: set[str] | None = None) -> list[TaskEnvelope]:
        items: list[TaskEnvelope] = []
        for path in sorted(self.tasks_root.glob(f"{self.prefix}*.json")):
            task = self.load(path.stem.replace(self.prefix, "", 1))
            if task is None:
                continue
            if chat_id is not None and task.chat_id != chat_id:
                continue
            if statuses is not None and task.status not in statuses:
                continue
            items.append(task)
        items.sort(key=lambda item: item.created_at)
        return items

    def claim_ready(self, *, worker_id: str, lease_ttl_seconds: int = 300) -> TaskEnvelope | None:
        now = datetime.now(timezone.utc)
        for task in self.list_tasks():
            if task.status in {"leased", "running"} and task.lease and self._lease_expired(task.lease, now=now):
                if not self.can_retry(task):
                    self.fail(task, error=task.last_attempt_error or task.error or "Retry budget exhausted")
                    continue
            if not self._is_claimable(task, now=now):
                continue
            task.attempt_count += 1
            task.retry_not_before = None
            task.lease = self._build_lease(
                worker_id=worker_id,
                now=now,
                ttl_seconds=lease_ttl_seconds,
                attempt=task.attempt_count,
            )
            task.status = "leased"
            task.updated_at = utc_now_iso()
            self.save(task)
            return task
        return None

    def heartbeat(self, task: TaskEnvelope, *, worker_id: str | None = None, lease_ttl_seconds: int = 300) -> TaskEnvelope:
        now = datetime.now(timezone.utc)
        worker = worker_id or (task.lease.worker_id if task.lease else "worker")
        attempt = task.attempt_count if task.attempt_count > 0 else 1
        task.lease = self._build_lease(worker_id=worker, now=now, ttl_seconds=lease_ttl_seconds, attempt=attempt)
        task.updated_at = utc_now_iso()
        self.save(task)
        return task

    def release(self, task: TaskEnvelope, *, status: str = "queued") -> TaskEnvelope:
        task.status = status
        task.lease = None
        task.updated_at = utc_now_iso()
        self.save(task)
        return task

    def mark_running(self, task: TaskEnvelope, *, run_id: str | None = None) -> TaskEnvelope:
        task.status = "running"
        task.run_id = run_id or task.run_id
        task = self.heartbeat(task, worker_id=task.lease.worker_id if task.lease else None)
        task.updated_at = utc_now_iso()
        self.save(task)
        return task

    def complete(
        self,
        task: TaskEnvelope,
        *,
        run_id: str,
        result_envelope_path: str,
        result_summary: str,
        artifact_paths: list[str],
    ) -> TaskEnvelope:
        task.status = "completed"
        task.run_id = run_id
        task.result_envelope_path = result_envelope_path
        task.result_summary = result_summary
        task.artifact_paths = artifact_paths
        task.retry_not_before = None
        task.last_attempt_error = None
        task.last_error = None
        task.error = None
        task.lease = None
        task.updated_at = utc_now_iso()
        self.save(task)
        return task

    def retry(self, task: TaskEnvelope, *, error: str, delay_seconds: int = 5) -> TaskEnvelope:
        task.last_attempt_error = error
        task.last_error = error
        task.error = None
        task.lease = None
        if self.can_retry(task):
            task.status = "queued"
            retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
            task.retry_not_before = retry_at.replace(microsecond=0).isoformat()
        else:
            task.status = "failed"
            task.retry_not_before = None
            task.error = error
        task.updated_at = utc_now_iso()
        self.save(task)
        return task

    def fail(self, task: TaskEnvelope, *, error: str) -> TaskEnvelope:
        task.status = "failed"
        task.last_attempt_error = error
        task.last_error = error
        task.error = error
        task.retry_not_before = None
        task.lease = None
        task.updated_at = utc_now_iso()
        self.save(task)
        return task

    def cancel(self, task: TaskEnvelope) -> TaskEnvelope:
        task.status = "cancelled"
        task.retry_not_before = None
        task.lease = None
        task.updated_at = utc_now_iso()
        self.save(task)
        return task

    def confirm(self, task: TaskEnvelope) -> TaskEnvelope:
        if task.confirmation_request:
            task.confirmation_request.status = "confirmed"
            task.confirmation_request.updated_at = utc_now_iso()
        task.status = "queued"
        task.retry_not_before = None
        task.updated_at = utc_now_iso()
        self.save(task)
        return task

    def reject(self, task: TaskEnvelope) -> TaskEnvelope:
        if task.confirmation_request:
            task.confirmation_request.status = "rejected"
            task.confirmation_request.updated_at = utc_now_iso()
        return self.cancel(task)

    def can_retry(self, task: TaskEnvelope) -> bool:
        return task.attempt_count < task.max_attempts

    def path_for(self, task_id: str) -> Path:
        return self.tasks_root / f"{self.prefix}{task_id}.json"

    def _is_claimable(self, task: TaskEnvelope, *, now: datetime) -> bool:
        if task.status == "awaiting_confirmation":
            return False
        if task.status == "queued":
            retry_at = _parse_iso(task.retry_not_before)
            return retry_at is None or retry_at <= now
        if task.status in {"leased", "running"} and task.lease and self._lease_expired(task.lease, now=now):
            return True
        return False

    def _lease_expired(self, lease: TaskLease, *, now: datetime) -> bool:
        expires = _parse_iso(lease.lease_expires_at)
        if expires is None:
            return True
        return expires <= now

    def _build_lease(self, *, worker_id: str, now: datetime, ttl_seconds: int, attempt: int) -> TaskLease:
        issued_at = now.replace(microsecond=0).isoformat()
        expires_at = (now + timedelta(seconds=ttl_seconds)).replace(microsecond=0).isoformat()
        return TaskLease(
            worker_id=worker_id,
            leased_at=issued_at,
            lease_expires_at=expires_at,
            attempt=attempt,
            last_heartbeat_at=issued_at,
        )
