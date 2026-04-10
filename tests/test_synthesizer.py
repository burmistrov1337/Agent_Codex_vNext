from __future__ import annotations

import unittest

from agent_codex.contracts import Artifact, SynthesisInput, WorkerResult
from agent_codex.runtime import Synthesizer


class SynthesizerTests(unittest.TestCase):
    def test_synthesizer_prefers_useful_worker_output(self) -> None:
        synthesizer = Synthesizer()
        outcome = synthesizer.synthesize(
            SynthesisInput(
                request="Сделай вывод",
                mode="interactive",
                task_graph=["researcher: собрать данные"],
                worker_results=[
                    WorkerResult(
                        task_id="1",
                        role="researcher",
                        status="completed",
                        summary="Коротко",
                        output="Содержательный ответ по существу.",
                        evidence=["file:a", "file:b"],
                        follow_up_actions=["Проверить вывод."],
                    )
                ],
                artifacts=[Artifact(path="summary.md", kind="markdown", label="Summary")],
            )
        )
        self.assertEqual(outcome.final_summary, "Содержательный ответ по существу.")
        self.assertIn("Артефакт готов", outcome.facts[0])
        self.assertEqual(outcome.next_actions, ["Проверить вывод."])


if __name__ == "__main__":
    unittest.main()
