from __future__ import annotations

from dataclasses import dataclass

from ..contracts import Task, WorkerContext


@dataclass(slots=True)
class BackendResponse:
    summary: str
    output: str
    gaps: list[str] | None = None
    follow_up_actions: list[str] | None = None


class BackendAdapter:
    name = "base"

    def run(self, task: Task, context: WorkerContext) -> BackendResponse:
        raise NotImplementedError


class DeterministicBackendAdapter(BackendAdapter):
    name = "deterministic"

    def run(self, task: Task, context: WorkerContext) -> BackendResponse:
        summary = f"{task.role} обработал задачу: {task.goal}"
        output = (
            f"Роль: {task.role}\n"
            f"Цель: {task.goal}\n"
            f"Режим: {context.mode}\n"
            f"Запрос: {context.request}\n"
            "Требование к синтезу: координатор обязан превратить результат в конкретный spec."
        )
        return BackendResponse(
            summary=summary,
            output=output,
            gaps=["Structured synthesis is still shallow in deterministic mode."],
            follow_up_actions=["Собрать coordinator-owned synthesis для этого worker output."],
        )


class NullBackendAdapter(BackendAdapter):
    name = "null"

    def run(self, task: Task, context: WorkerContext) -> BackendResponse:
        return BackendResponse(summary=f"{task.role}: backend не подключён", output="Backend is not configured.")


def select_backend(name: str) -> BackendAdapter:
    normalized = (name or "deterministic").strip().lower()
    if normalized == "deterministic":
        return DeterministicBackendAdapter()
    return NullBackendAdapter()
