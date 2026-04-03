from __future__ import annotations

import re

from ..contracts import SynthesisOutcome, Task, TaskGraph, WorkerResult


FORBIDDEN_SYNTHESIS_PHRASES = (
    "based on your findings",
    "based on the research",
    "worker found",
)


class Coordinator:
    def build_task_graph(self, request: str, *, domain: str = "general") -> TaskGraph:
        lowered = request.lower()
        if domain == "marketplace" or "wildberries" in lowered or "маркетплейс" in lowered:
            tasks = [
                Task(id="market-1", kind="analysis", role="marketplace_analyst", goal="Собрать факты и сигналы по данным", priority=10),
                Task(id="market-2", kind="critique", role="critic", goal="Оспорить выводы и найти недоказанные места", dependencies=["market-1"], priority=20),
                Task(id="market-3", kind="review", role="reviewer", goal="Проверить полноту результата и критерии готовности", dependencies=["market-2"], priority=30),
            ]
        else:
            tasks = [
                Task(id="gen-1", kind="analysis", role="business_analyst", goal="Структурировать задачу и требования", priority=10),
                Task(id="gen-2", kind="draft", role="writer", goal="Подготовить понятную форму результата", dependencies=["gen-1"], priority=20),
                Task(id="gen-3", kind="critique", role="critic", goal="Оспорить слабые места и допущения", dependencies=["gen-2"], priority=30),
                Task(id="gen-4", kind="review", role="reviewer", goal="Проверить полноту и зрелость решения", dependencies=["gen-3"], priority=40),
            ]
        rules = [
            "Нельзя делегировать ленивыми фразами вроде 'based on your findings'.",
            "Координатор обязан прочитать результаты workers и перевести их в конкретные действия.",
            "Финальная сводка должна содержать факты, ограничения и следующие шаги.",
        ]
        return TaskGraph(tasks=tasks, synthesis_rules=rules)

    def validate_synthesis(self, text: str) -> list[str]:
        lowered = text.lower()
        violations = [phrase for phrase in FORBIDDEN_SYNTHESIS_PHRASES if phrase in lowered]
        if re.search(r"\bbased on\b", lowered) and not violations:
            violations.append("generic based on phrasing")
        return violations

    def decide_continuation(self, worker_results: list[WorkerResult], synthesis: SynthesisOutcome) -> SynthesisOutcome:
        gaps = [gap for item in worker_results for gap in item.gaps]
        follow_ups = [action for item in worker_results for action in item.follow_up_actions]
        roles = [item.role for item in worker_results]

        if gaps:
            synthesis.continuation_strategy = "continue_existing_branch"
            synthesis.suggested_role = roles[0] if roles else None
            synthesis.next_step_spec = {
                "action": "continue_existing_branch",
                "owner_role": synthesis.suggested_role,
                "goal": "Уточнить недоказанные места и закрыть gaps перед новым workstream.",
                "blocking_gaps": gaps[:4],
                "input_refs": [f"worker:{item.task_id}" for item in worker_results[:3]],
                "done_when": ["Gaps закрыты", "Есть один конкретный deliverable"],
                "spawn_ready": False,
            }
            return synthesis

        if len(set(roles)) >= 3 and follow_ups:
            synthesis.continuation_strategy = "spawn_new_branch"
            synthesis.suggested_role = "coordinator"
            synthesis.next_step_spec = {
                "action": "spawn_new_branch",
                "owner_role": "coordinator",
                "goal": "Собрать scoped subtask из follow-up действий и отдать его как отдельную ветку.",
                "blocking_gaps": [],
                "input_refs": [f"worker:{item.task_id}" for item in worker_results[:3]],
                "done_when": ["Новый subtask scoped", "Нет дублирования уже выполненной работы"],
                "spawn_ready": True,
            }
            return synthesis

        synthesis.continuation_strategy = "continue_existing_branch"
        synthesis.suggested_role = roles[-1] if roles else None
        synthesis.next_step_spec = {
            "action": "continue_existing_branch",
            "owner_role": synthesis.suggested_role,
            "goal": "Продолжить текущую ветку и перевести результат в следующий конкретный deliverable.",
            "blocking_gaps": [],
            "input_refs": [f"worker:{item.task_id}" for item in worker_results[:3]],
            "done_when": ["Есть следующий конкретный deliverable"],
            "spawn_ready": False,
        }
        return synthesis
