from __future__ import annotations

import json
import urllib.error
import urllib.request
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
            "Требование к синтезу: координатор обязан превратить результат в конкретный следующий шаг."
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
        return BackendResponse(
            summary=f"{task.role}: backend не подключён",
            output="Backend is not configured.",
        )


class GroqBackendAdapter(BackendAdapter):
    name = "groq"

    def __init__(self, *, api_key: str | None, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def run(self, task: Task, context: WorkerContext) -> BackendResponse:
        if not self.api_key:
            return BackendResponse(
                summary=f"{task.role}: Groq API key не настроен",
                output="Не удалось получить ответ от Groq, потому что на сервере не настроен API key.",
                gaps=["Missing GROQ_API_KEY for live answer generation."],
                follow_up_actions=["Добавить GROQ_API_KEY в server .env."],
            )

        system_prompt = (
            "Ты помогаешь как специализированная роль в агентной системе. "
            "Отвечай на русском, коротко и по делу. "
            "Нельзя писать пустые служебные фразы вроде 'задача обработана'. "
            "Нужно вернуть JSON-объект со строго четырьмя полями: "
            "summary, output, gaps, follow_up_actions. "
            "summary — одна короткая строка сути результата. "
            "output — полезный ответ пользователю по существу, без внутренней кухни. "
            "gaps — массив реальных ограничений, если они есть. "
            "follow_up_actions — массив практичных следующих шагов."
        )
        user_prompt = (
            f"Роль: {task.role}\n"
            f"Цель роли: {task.goal}\n"
            f"Режим: {context.mode}\n"
            f"Запрос пользователя:\n{context.request}\n\n"
            "Верни только JSON без markdown."
        )
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": 800,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        request = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return BackendResponse(
                summary=f"{task.role}: Groq HTTP {exc.code}",
                output="Не удалось получить содержательный ответ от серверного LLM.",
                gaps=[f"Groq HTTP error {exc.code}: {body[:300]}"],
                follow_up_actions=["Проверить модель, ключ и лимиты Groq."],
            )
        except Exception as exc:  # noqa: BLE001
            return BackendResponse(
                summary=f"{task.role}: ошибка Groq backend",
                output="Не удалось получить содержательный ответ от серверного LLM.",
                gaps=[str(exc)[:300]],
                follow_up_actions=["Проверить сетевой доступ VPS к Groq API."],
            )

        content = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return BackendResponse(
                summary=f"{task.role}: ответ Groq без JSON",
                output=content[:1200] or "Модель вернула пустой ответ.",
                gaps=["Groq response was not valid JSON."],
                follow_up_actions=["Упростить prompt или смягчить response parsing."],
            )

        summary = str(parsed.get("summary") or f"{task.role}: ответ подготовлен").strip()
        output = str(parsed.get("output") or summary).strip()
        gaps = [str(item).strip() for item in (parsed.get("gaps") or []) if str(item).strip()]
        follow_up = [str(item).strip() for item in (parsed.get("follow_up_actions") or []) if str(item).strip()]
        return BackendResponse(
            summary=summary[:300],
            output=output[:4000],
            gaps=gaps[:6],
            follow_up_actions=follow_up[:6],
        )


def select_backend(
    name: str,
    *,
    groq_api_key: str | None = None,
    groq_model: str = "llama-3.3-70b-versatile",
) -> BackendAdapter:
    normalized = (name or "deterministic").strip().lower()
    if normalized == "groq":
        return GroqBackendAdapter(api_key=groq_api_key, model=groq_model)
    if normalized == "deterministic":
        return DeterministicBackendAdapter()
    return NullBackendAdapter()
