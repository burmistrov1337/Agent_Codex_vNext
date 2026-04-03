from __future__ import annotations

from ..contracts import SynthesisInput, SynthesisOutcome


class Synthesizer:
    def synthesize(self, synthesis_input: SynthesisInput) -> SynthesisOutcome:
        facts: list[str] = []
        limitations: list[str] = list(synthesis_input.alerts)
        next_actions: list[str] = []

        for artifact in synthesis_input.artifacts:
            facts.append(f"Артефакт готов: {artifact.label}")

        for result in synthesis_input.worker_results:
            if result.evidence:
                facts.append(f"{result.role}: {', '.join(result.evidence[:2])}")
            limitations.extend(result.gaps)
            next_actions.extend(result.follow_up_actions)

        if not next_actions:
            next_actions.append("Координатору стоит перевести результат в следующий конкретный шаг без ленивого handoff.")

        facts = list(dict.fromkeys(facts))
        limitations = list(dict.fromkeys(limitations))
        next_actions = list(dict.fromkeys(next_actions))

        summary = (
            f"Собран прогон в режиме {synthesis_input.mode}. "
            f"Задач в графе: {len(synthesis_input.task_graph)}. "
            f"Получено результатов workers: {len(synthesis_input.worker_results)}."
        )
        user_message = (
            "Готово. Собрал результат и свёл его в один понятный ответ. "
            "Если хочешь, следующим сообщением могу продолжить уже по следующему конкретному шагу."
        )
        return SynthesisOutcome(
            final_summary=summary,
            user_message=user_message,
            facts=facts[:6],
            limitations=limitations[:6],
            next_actions=next_actions[:6],
            continuation_strategy="continue_existing_branch",
            next_step_spec={
                "action": "continue_existing_branch",
                "owner_role": None,
                "goal": "Собрать следующий конкретный шаг из worker results.",
                "blocking_gaps": limitations[:3],
                "input_refs": [],
                "done_when": ["Есть один конкретный следующий deliverable."],
                "spawn_ready": False,
            },
        )
