from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
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


def _system_prompt() -> str:
    return (
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


def _user_prompt(task: Task, context: WorkerContext) -> str:
    return (
        f"Роль: {task.role}\n"
        f"Цель роли: {task.goal}\n"
        f"Режим: {context.mode}\n"
        f"Запрос пользователя:\n{context.request}\n\n"
        "Верни только JSON без markdown."
    )


class JsonHttpBackendAdapter(BackendAdapter, ABC):
    api_label = "backend"

    def __init__(self, *, api_key: str | None, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def run(self, task: Task, context: WorkerContext) -> BackendResponse:
        if not self.api_key:
            return BackendResponse(
                summary=f"{task.role}: {self.api_label} API key не настроен",
                output=f"Не удалось получить ответ от {self.api_label}, потому что API key не настроен.",
                gaps=[f"Missing API key for {self.api_label} live answer generation."],
                follow_up_actions=[f"Добавить API key для {self.api_label} в .env."],
            )

        try:
            raw = self._request_completion(task, context)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return BackendResponse(
                summary=f"{task.role}: {self.api_label} HTTP {exc.code}",
                output="Не удалось получить содержательный ответ от LLM backend.",
                gaps=[f"{self.api_label} HTTP error {exc.code}: {body[:300]}"],
                follow_up_actions=[f"Проверить модель, ключ и лимиты {self.api_label}."],
            )
        except Exception as exc:  # noqa: BLE001
            return BackendResponse(
                summary=f"{task.role}: ошибка {self.api_label} backend",
                output="Не удалось получить содержательный ответ от LLM backend.",
                gaps=[str(exc)[:300]],
                follow_up_actions=[f"Проверить сетевой доступ к {self.api_label} API."],
            )

        content = self._extract_content(raw)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return BackendResponse(
                summary=f"{task.role}: ответ {self.api_label} без JSON",
                output=content[:1200] or "Модель вернула пустой ответ.",
                gaps=[f"{self.api_label} response was not valid JSON."],
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

    def _request_completion(self, task: Task, context: WorkerContext) -> dict:
        request = urllib.request.Request(
            self.endpoint(),
            data=json.dumps(self.build_payload(task, context), ensure_ascii=False).encode("utf-8"),
            headers=self.build_headers(),
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))

    @abstractmethod
    def endpoint(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def build_headers(self) -> dict[str, str]:
        raise NotImplementedError

    @abstractmethod
    def build_payload(self, task: Task, context: WorkerContext) -> dict:
        raise NotImplementedError

    @abstractmethod
    def _extract_content(self, raw: dict) -> str:
        raise NotImplementedError


class GroqBackendAdapter(JsonHttpBackendAdapter):
    name = "groq"
    api_label = "Groq"

    def endpoint(self) -> str:
        return "https://api.groq.com/openai/v1/chat/completions"

    def build_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def build_payload(self, task: Task, context: WorkerContext) -> dict:
        return {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": 800,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": _user_prompt(task, context)},
            ],
        }

    def _extract_content(self, raw: dict) -> str:
        return raw.get("choices", [{}])[0].get("message", {}).get("content", "")


class OpenAIBackendAdapter(JsonHttpBackendAdapter):
    name = "openai"
    api_label = "OpenAI"

    def endpoint(self) -> str:
        return "https://api.openai.com/v1/chat/completions"

    def build_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def build_payload(self, task: Task, context: WorkerContext) -> dict:
        return {
            "model": self.model,
            "temperature": 0.2,
            "max_completion_tokens": 800,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": _user_prompt(task, context)},
            ],
        }

    def _extract_content(self, raw: dict) -> str:
        return raw.get("choices", [{}])[0].get("message", {}).get("content", "")


class AnthropicBackendAdapter(JsonHttpBackendAdapter):
    name = "anthropic"
    api_label = "Anthropic"

    def endpoint(self) -> str:
        return "https://api.anthropic.com/v1/messages"

    def build_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": str(self.api_key),
            "anthropic-version": "2023-06-01",
        }

    def build_payload(self, task: Task, context: WorkerContext) -> dict:
        return {
            "model": self.model,
            "max_tokens": 800,
            "temperature": 0.2,
            "system": _system_prompt(),
            "messages": [
                {"role": "user", "content": _user_prompt(task, context)},
            ],
        }

    def _extract_content(self, raw: dict) -> str:
        content = raw.get("content", [])
        return "".join(item.get("text", "") for item in content if item.get("type") == "text")


class OllamaBackendAdapter(JsonHttpBackendAdapter):
    name = "ollama"
    api_label = "Ollama"

    def __init__(self, *, base_url: str, model: str) -> None:
        super().__init__(api_key="local", model=model)
        self.base_url = base_url.rstrip("/")

    def endpoint(self) -> str:
        return f"{self.base_url}/api/chat"

    def build_headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def build_payload(self, task: Task, context: WorkerContext) -> dict:
        return {
            "model": self.model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
            "messages": [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": _user_prompt(task, context)},
            ],
        }

    def _extract_content(self, raw: dict) -> str:
        return raw.get("message", {}).get("content", "")


def select_backend(
    name: str,
    *,
    groq_api_key: str | None = None,
    groq_model: str = "llama-3.3-70b-versatile",
    openai_api_key: str | None = None,
    openai_model: str = "gpt-5.4-mini",
    anthropic_api_key: str | None = None,
    anthropic_model: str = "claude-sonnet-4-5",
    ollama_base_url: str = "http://127.0.0.1:11434",
    ollama_model: str = "llama3.1:8b",
) -> BackendAdapter:
    normalized = (name or "deterministic").strip().lower()
    if normalized == "groq":
        return GroqBackendAdapter(api_key=groq_api_key, model=groq_model)
    if normalized == "openai":
        return OpenAIBackendAdapter(api_key=openai_api_key, model=openai_model)
    if normalized == "anthropic":
        return AnthropicBackendAdapter(api_key=anthropic_api_key, model=anthropic_model)
    if normalized == "ollama":
        return OllamaBackendAdapter(base_url=ollama_base_url, model=ollama_model)
    if normalized == "deterministic":
        return DeterministicBackendAdapter()
    return NullBackendAdapter()
