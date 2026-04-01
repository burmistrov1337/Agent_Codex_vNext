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
