from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agent_codex.apps.cli.main import main
from agent_codex.config import ensure_runtime_layout, load_settings
from agent_codex.domains.marketplace.artifacts import (
    render_watch_dashboard_html,
    render_watch_summary_markdown,
)
from agent_codex.hooks import HookPipeline
from agent_codex.hooks.policy import evaluate_tool_action
from agent_codex.integrations.telegram_raw import TelegramNotifyError
from agent_codex.memory import ConsolidationEngine, MemoryStore
from agent_codex.runtime import AgentExecutor, Coordinator, TelegramBotService


class FakeTelegramAdapter:
    def __init__(self, *, allowed_chat_id: str = "413513309") -> None:
        self.allowed_chat_id = allowed_chat_id
        self.is_configured = True
        self._updates: list[dict] = []
        self._downloads: dict[str, bytes] = {}
        self.sent_texts: list[dict] = []
        self.sent_files: list[dict] = []

    def is_chat_allowed(self, chat_id: str) -> bool:
        return str(chat_id) == str(self.allowed_chat_id)

    def queue_update(self, update: dict) -> None:
        self._updates.append(update)

    def queue_download(self, file_id: str, content: bytes) -> None:
        self._downloads[file_id] = content

    def poll_updates(self, *, offset: int | None = None, limit: int = 20) -> list[dict]:
        items = [item for item in self._updates if offset is None or int(item["update_id"]) >= int(offset)]
        return items[:limit]

    def download_file(self, file_id: str, destination: str | Path) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self._downloads.get(file_id, b"stub"))
        return target

    def send_text_to_chat(self, chat_id: str, text: str, *, reply_to_message_id: int | None = None) -> dict:
        self.sent_texts.append(
            {
                "chat_id": str(chat_id),
                "text": text,
                "reply_to_message_id": reply_to_message_id,
            }
        )
        return {"ok": True}

    def send_file_to_chat(
        self,
        chat_id: str,
        file_path: str | Path,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> dict:
        self.sent_files.append(
            {
                "chat_id": str(chat_id),
                "file_path": str(file_path),
                "caption": caption,
                "reply_to_message_id": reply_to_message_id,
            }
        )
        return {"ok": True}


class ConflictTelegramAdapter(FakeTelegramAdapter):
    def poll_updates(self, *, offset: int | None = None, limit: int = 20) -> list[dict]:
        raise TelegramNotifyError('Telegram HTTP 409: {"ok":false,"error_code":409}')


def build_message_update(
    update_id: int,
    *,
    chat_id: str = "413513309",
    message_id: int = 1,
    text: str | None = None,
    caption: str | None = None,
    document: dict | None = None,
    photo: list[dict] | None = None,
) -> dict:
    payload: dict = {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "chat": {"id": int(chat_id), "type": "private"},
        },
    }
    if text is not None:
        payload["message"]["text"] = text
    if caption is not None:
        payload["message"]["caption"] = caption
    if document is not None:
        payload["message"]["document"] = document
    if photo is not None:
        payload["message"]["photo"] = photo
    return payload


class VNextTests(unittest.TestCase):
    def _make_runtime(self, tmp: str):
        settings = load_settings(tmp)
        ensure_runtime_layout(settings)
        memory = MemoryStore(settings)
        executor = AgentExecutor(
            settings=settings,
            coordinator=Coordinator(),
            hooks=HookPipeline(settings),
            memory=memory,
        )
        return settings, memory, executor

    def test_protected_file_is_blocked(self) -> None:
        with TemporaryDirectory() as tmp:
            settings = load_settings(tmp)
            ensure_runtime_layout(settings)
            decision = evaluate_tool_action("write_file", target_path=str(Path(tmp) / ".env"))
            self.assertFalse(decision.allowed)
            self.assertEqual(decision.risk, "high")

    def test_scratchpad_is_allowed(self) -> None:
        with TemporaryDirectory() as tmp:
            settings = load_settings(tmp)
            ensure_runtime_layout(settings)
            scratch = settings.runtime_root / "scratchpad" / "handoff.json"
            decision = evaluate_tool_action(
                "write_file",
                target_path=str(scratch),
                scratchpad_root=str(settings.runtime_root / "scratchpad"),
            )
            self.assertTrue(decision.allowed)
            self.assertIn("scratchpad-allow", decision.matched_rules)

    def test_memory_store_updates_index(self) -> None:
        with TemporaryDirectory() as tmp:
            settings = load_settings(tmp)
            ensure_runtime_layout(settings)
            store = MemoryStore(settings)
            topic = store.remember(title="Marketplace Notes", body="Important facts.")
            self.assertTrue(topic.exists())
            index = store.index_path.read_text(encoding="utf-8")
            self.assertIn("Marketplace Notes", index)

    def test_consolidation_gates_respected(self) -> None:
        with TemporaryDirectory() as tmp:
            settings = load_settings(tmp)
            ensure_runtime_layout(settings)
            engine = ConsolidationEngine(settings)
            ready, reason = engine.should_run()
            self.assertFalse(ready)
            self.assertTrue("session gate" in reason or "time gate" in reason)

    def test_coordinator_marketplace_graph_has_quality_gates(self) -> None:
        graph = Coordinator().build_task_graph("Проверь Wildberries кабинет", domain="marketplace")
        roles = [task.role for task in graph.tasks]
        self.assertEqual(roles, ["marketplace_analyst", "critic", "reviewer"])

    def test_marketplace_watch_headless_run_returns_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            settings, memory, executor = self._make_runtime(tmp)
            envelope = executor.run_marketplace_watch(top_limit=10, sample_data=True, headless=True)
            self.assertTrue(envelope.final_summary)
            self.assertTrue(any(item.kind == "html" for item in envelope.artifacts))
            self.assertTrue(any("marketplace_analyst" in line for line in envelope.task_graph))
            self.assertTrue(settings.marketplace_artifact_root.exists())
            self.assertTrue(memory.index_path.exists())

    def test_doctor_command_json(self) -> None:
        with TemporaryDirectory() as tmp:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                rc = main(["doctor", "--project-root", str(tmp), "--json"])
            self.assertEqual(rc, 0)
            payload = json.loads(buffer.getvalue())
            self.assertIn("runtime_root", payload)

    def test_marketplace_watch_headless_json(self) -> None:
        with TemporaryDirectory() as tmp:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                rc = main(
                    [
                        "marketplace-watch",
                        "--project-root",
                        str(tmp),
                        "--sample-data",
                        "--headless",
                    ]
                )
            self.assertEqual(rc, 0)
            payload = json.loads(buffer.getvalue())
            self.assertTrue(payload["final_summary"])
            self.assertTrue(payload["artifacts"])

    def test_dashboard_and_summary_render(self) -> None:
        with TemporaryDirectory() as tmp:
            snapshot_path = Path(tmp) / "history.jsonl"
            snapshot_path.write_text("", encoding="utf-8")
            rows = [
                {
                    "status": "decline",
                    "title": "Бромелаин 5г",
                    "sales_30d": 12,
                    "sales_prev_30d": 20,
                    "sales_delta_pct": -40,
                    "stock": 24,
                    "actions": "Проверить карточку",
                    "issues": "Падение продаж",
                    "subject_name": "Косметические активы",
                    "description": "Актив для косметики",
                    "nm_id": 1001,
                    "priority_score": 50,
                    "revenue_30d": 12000,
                    "discounted_price": 1260,
                },
                {
                    "status": "growth",
                    "title": "Церамиды 30г",
                    "sales_30d": 40,
                    "sales_prev_30d": 15,
                    "sales_delta_pct": 166.7,
                    "stock": 12,
                    "actions": "Не ломать работающую карточку",
                    "issues": "",
                    "subject_name": "Косметические активы",
                    "description": "Восстановление барьера кожи",
                    "nm_id": 1002,
                    "priority_score": 10,
                    "revenue_30d": 36000,
                    "discounted_price": 1805,
                },
            ]
            summary = render_watch_summary_markdown(rows=rows, today=date(2026, 4, 1), snapshot_path=snapshot_path)
            dashboard = render_watch_dashboard_html(rows=rows, today=date(2026, 4, 1), snapshot_path=snapshot_path)
            self.assertIn("Регулярный мониторинг кабинета Wildberries", summary)
            self.assertIn("<html", dashboard.lower())

    def test_telegram_bot_ignores_unauthorized_chat(self) -> None:
        with TemporaryDirectory() as tmp:
            settings, memory, executor = self._make_runtime(tmp)
            telegram = FakeTelegramAdapter(allowed_chat_id="1")
            telegram.queue_update(build_message_update(100, chat_id="999", message_id=10, text="/ask Привет"))
            service = TelegramBotService(settings=settings, executor=executor, telegram=telegram, memory=memory)
            payload = service.run_polling(once=True)
            self.assertEqual(payload["processed_updates"], 1)
            self.assertEqual(telegram.sent_texts, [])

    def test_telegram_bot_processes_safe_ask_and_sends_final_result(self) -> None:
        with TemporaryDirectory() as tmp:
            settings, memory, executor = self._make_runtime(tmp)
            telegram = FakeTelegramAdapter()
            telegram.queue_update(build_message_update(101, message_id=11, text="/ask Подготовь краткую сводку по задаче"))
            service = TelegramBotService(settings=settings, executor=executor, telegram=telegram, memory=memory)
            payload = service.run_polling(once=True)
            self.assertEqual(payload["executed_tasks"], 1)
            self.assertGreaterEqual(len(telegram.sent_texts), 2)
            self.assertIn("Принято в работу", telegram.sent_texts[0]["text"])
            self.assertIn("Готово.", telegram.sent_texts[-1]["text"])
            self.assertEqual(len(telegram.sent_files), 0)

    def test_telegram_bot_requires_confirm_for_risky_request(self) -> None:
        with TemporaryDirectory() as tmp:
            settings, memory, executor = self._make_runtime(tmp)
            telegram = FakeTelegramAdapter()
            telegram.queue_update(build_message_update(102, message_id=12, text="/ask Сделай git commit и push"))
            service = TelegramBotService(settings=settings, executor=executor, telegram=telegram, memory=memory)
            first_pass = service.run_polling(once=True)
            self.assertEqual(first_pass["executed_tasks"], 0)
            self.assertEqual(len(telegram.sent_texts), 1)
            self.assertIn("нужно подтверждение", telegram.sent_texts[0]["text"].lower())

            telegram.queue_update(build_message_update(103, message_id=13, text="/confirm"))
            second_pass = service.run_polling(once=True)
            self.assertEqual(second_pass["executed_tasks"], 1)
            self.assertGreaterEqual(len(telegram.sent_texts), 3)
            self.assertIn("Подтверждение принято", telegram.sent_texts[1]["text"])
            self.assertIn("Готово.", telegram.sent_texts[-1]["text"])

    def test_telegram_bot_downloads_document_and_sends_summary_file(self) -> None:
        with TemporaryDirectory() as tmp:
            settings, memory, executor = self._make_runtime(tmp)
            telegram = FakeTelegramAdapter()
            telegram.queue_download("doc-file-id", "Привет из txt".encode("utf-8"))
            telegram.queue_update(
                build_message_update(
                    104,
                    message_id=14,
                    text="Проанализируй вложение",
                    document={
                        "file_id": "doc-file-id",
                        "file_name": "notes.txt",
                        "mime_type": "text/plain",
                        "file_size": 14,
                    },
                )
            )
            service = TelegramBotService(settings=settings, executor=executor, telegram=telegram, memory=memory)
            service.run_polling(once=True)
            self.assertGreaterEqual(len(telegram.sent_texts), 2)
            self.assertEqual(len(telegram.sent_files), 1)
            self.assertTrue(telegram.sent_files[0]["file_path"].endswith(".md"))
            inbox_files = list((settings.telegram_inbox_root).rglob("notes.txt"))
            self.assertTrue(inbox_files)

    def test_telegram_bot_status_and_cancel(self) -> None:
        with TemporaryDirectory() as tmp:
            settings, memory, executor = self._make_runtime(tmp)
            telegram = FakeTelegramAdapter()
            service = TelegramBotService(settings=settings, executor=executor, telegram=telegram, memory=memory)

            task_dir = settings.runtime_root / "tasks"
            task_dir.mkdir(parents=True, exist_ok=True)
            queued_task = {
                "task_id": "manual-1",
                "source": "telegram",
                "command": "ask",
                "request": "Очередная задача",
                "chat_id": "413513309",
                "message_id": 15,
                "session_id": "telegram-413513309",
                "status": "queued",
                "attachments": [],
                "risky": False,
                "confirmation_request": None,
                "result_summary": None,
                "artifact_paths": [],
                "error": None,
                "created_at": "2026-04-02T00:00:00+00:00",
                "updated_at": "2026-04-02T00:00:00+00:00",
            }
            (task_dir / "telegram_manual-1.json").write_text(json.dumps(queued_task, ensure_ascii=False), encoding="utf-8")
            telegram.queue_update(build_message_update(105, message_id=15, text="/status"))
            telegram.queue_update(build_message_update(106, message_id=16, text="/cancel"))
            service.run_polling(once=True)
            self.assertIn("Последние задачи", telegram.sent_texts[0]["text"])
            self.assertIn("Отменил задачу", telegram.sent_texts[1]["text"])

    def test_telegram_bot_handles_polling_conflict_gracefully(self) -> None:
        with TemporaryDirectory() as tmp:
            settings, memory, executor = self._make_runtime(tmp)
            telegram = ConflictTelegramAdapter()
            service = TelegramBotService(settings=settings, executor=executor, telegram=telegram, memory=memory)
            payload = service.run_polling(once=True)
            self.assertEqual(payload["processed_updates"], 0)
            self.assertEqual(payload["executed_tasks"], 0)
            self.assertIn("409", payload["last_error"])

    def test_telegram_bot_cli_once_json(self) -> None:
        with TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "TELEGRAM_BOT_TOKEN=dummy",
                        "TELEGRAM_CHAT_ID=413513309",
                        "TELEGRAM_ALLOWED_CHAT_ID=413513309",
                    ]
                ),
                encoding="utf-8",
            )
            buffer = io.StringIO()
            with patch("agent_codex.apps.cli.main.TelegramBotService.run_polling", return_value={"cycles": 1, "processed_updates": 0, "executed_tasks": 0, "allowed_chat_id": "413513309"}):
                with redirect_stdout(buffer):
                    rc = main(["telegram-bot", "--project-root", tmp, "--once", "--json"])
            self.assertEqual(rc, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["cycles"], 1)
            self.assertIn("allowed_chat_id", payload)


if __name__ == "__main__":
    unittest.main()
