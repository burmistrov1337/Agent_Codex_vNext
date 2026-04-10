from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from agent_codex.contracts import Task, WorkerContext
from agent_codex.integrations.llm import select_backend


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class LlmBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task = Task(id="t1", kind="worker", role="researcher", goal="Собрать факты")
        self.context = WorkerContext(
            run_id="run-1",
            request="Проверь состояние проекта",
            mode="interactive",
            selected_roles=["researcher"],
            project_root="D:/Agent_Codex_vNext",
            runtime_root="D:/Agent_Codex_vNext/.agent_codex",
            scratchpad_root="D:/Agent_Codex_vNext/.agent_codex/scratchpad",
        )

    def test_openai_backend_parses_json_response(self) -> None:
        backend = select_backend("openai", openai_api_key="key", openai_model="gpt-5.4-mini")
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "Готово",
                                "output": "Нашёл основные факты.",
                                "gaps": ["Не проверен прод."],
                                "follow_up_actions": ["Запустить smoke-test."],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }
        with patch("urllib.request.urlopen", return_value=_FakeResponse(payload)):
            response = backend.run(self.task, self.context)
        self.assertEqual(response.summary, "Готово")
        self.assertIn("Нашёл", response.output)
        self.assertEqual(response.gaps, ["Не проверен прод."])

    def test_anthropic_backend_parses_text_blocks(self) -> None:
        backend = select_backend("anthropic", anthropic_api_key="key", anthropic_model="claude-sonnet-4-5")
        payload = {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "summary": "Есть вывод",
                            "output": "Подготовил краткий ответ.",
                            "gaps": [],
                            "follow_up_actions": ["Уточнить входные данные."],
                        },
                        ensure_ascii=False,
                    ),
                }
            ]
        }
        with patch("urllib.request.urlopen", return_value=_FakeResponse(payload)):
            response = backend.run(self.task, self.context)
        self.assertEqual(response.summary, "Есть вывод")
        self.assertEqual(response.follow_up_actions, ["Уточнить входные данные."])

    def test_ollama_backend_handles_local_chat_payload(self) -> None:
        backend = select_backend("ollama", ollama_base_url="http://127.0.0.1:11434", ollama_model="llama3.1:8b")
        payload = {
            "message": {
                "content": json.dumps(
                    {
                        "summary": "Локально готово",
                        "output": "Ollama вернул структурированный ответ.",
                        "gaps": [],
                        "follow_up_actions": [],
                    },
                    ensure_ascii=False,
                )
            }
        }
        with patch("urllib.request.urlopen", return_value=_FakeResponse(payload)):
            response = backend.run(self.task, self.context)
        self.assertEqual(response.summary, "Локально готово")
        self.assertIn("Ollama", response.output)

    def test_missing_openai_key_returns_soft_failure(self) -> None:
        backend = select_backend("openai", openai_api_key=None)
        response = backend.run(self.task, self.context)
        self.assertIn("API key", response.summary)
        self.assertTrue(response.gaps)


if __name__ == "__main__":
    unittest.main()
