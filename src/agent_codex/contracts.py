from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class Task:
    id: str
    kind: str
    role: str
    goal: str
    inputs: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    priority: int = 50
    budget_policy: str = "default"


@dataclass(slots=True)
class TaskGraph:
    tasks: list[Task]
    synthesis_rules: list[str]

    def summarize(self) -> list[str]:
        return [f"{task.role}: {task.goal}" for task in self.tasks]


@dataclass(slots=True)
class WorkerContext:
    run_id: str
    request: str
    mode: str
    selected_roles: list[str]
    project_root: str
    runtime_root: str
    scratchpad_root: str


@dataclass(slots=True)
class TelegramAttachment:
    kind: str
    file_id: str
    file_name: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    local_path: str | None = None


@dataclass(slots=True)
class TelegramUpdateEnvelope:
    update_id: int
    chat_id: str
    message_id: int
    text: str
    command: str | None = None
    command_args: str | None = None
    caption: str | None = None
    attachments: list[TelegramAttachment] = field(default_factory=list)
    reply_to_message_id: int | None = None
    received_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class ConfirmationRequest:
    confirmation_id: str
    task_id: str
    chat_id: str
    prompt: str
    status: str = "pending"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class TelegramConversationSession:
    session_id: str
    chat_id: str
    created_at: str
    updated_at: str
    last_message_id: int | None = None
    last_task_id: str | None = None
    active_task_id: str | None = None
    pending_confirmation_id: str | None = None


@dataclass(slots=True)
class TaskEnvelope:
    task_id: str
    source: str
    command: str
    request: str
    chat_id: str
    message_id: int
    session_id: str
    status: str
    attachments: list[TelegramAttachment] = field(default_factory=list)
    risky: bool = False
    confirmation_request: ConfirmationRequest | None = None
    result_summary: str | None = None
    artifact_paths: list[str] = field(default_factory=list)
    error: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class Artifact:
    path: str
    kind: str
    label: str
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class WorkerResult:
    task_id: str
    role: str
    status: str
    summary: str
    output: str
    evidence: list[str] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class HookEvent:
    phase: str
    subject: str
    decision: str
    explanation: str
    risk: str
    timestamp: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class RunEnvelope:
    run_id: str
    request: str
    mode: str
    task_graph: list[str]
    results: list[WorkerResult]
    artifacts: list[Artifact]
    final_summary: str
    alerts: list[str]
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MemoryIndexEntry:
    title: str
    topic_path: str
    hook: str
    last_updated: str


def artifact_from_path(path: Path, kind: str, label: str) -> Artifact:
    return Artifact(path=str(path), kind=kind, label=label)
