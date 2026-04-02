from __future__ import annotations

import json
import mimetypes
import re
import time
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from ..config import Settings
from ..contracts import (
    ConfirmationRequest,
    RunEnvelope,
    TaskEnvelope,
    TelegramAttachment,
    TelegramConversationSession,
    TelegramUpdateEnvelope,
    utc_now_iso,
)
from ..integrations.telegram import TelegramAdapter
from ..integrations.telegram_raw import TelegramNotifyError
from ..memory import MemoryStore
from .executor import AgentExecutor


class TelegramBotService:
    def __init__(
        self,
        *,
        settings: Settings,
        executor: AgentExecutor,
        telegram: TelegramAdapter,
        memory: MemoryStore,
    ) -> None:
        self.settings = settings
        self.executor = executor
        self.telegram = telegram
        self.memory = memory
        self.tasks_root = settings.runtime_root / "tasks"
        self.telegram_root = settings.runtime_root / "telegram"
        self.telegram_sessions_root = self.telegram_root / "sessions"
        self.state_path = settings.telegram_state_root / "bot_state.json"

    def run_polling(self, *, once: bool = False, max_cycles: int | None = None) -> dict:
        cycles = 0
        processed_updates = 0
        executed_tasks = 0
        last_error: str | None = None
        while True:
            try:
                processed_updates += self.poll_once()
                executed_tasks += self.process_queue()
                last_error = None
            except TelegramNotifyError as exc:
                last_error = str(exc)
                self.memory.append_daily_log(
                    "Telegram polling issue",
                    f"Polling error: {last_error}",
                )
                if once:
                    break
                if "HTTP 409" in last_error:
                    time.sleep(3)
                    continue
                time.sleep(2)
            cycles += 1
            if once:
                break
            if max_cycles is not None and cycles >= max_cycles:
                break
        return {
            "cycles": cycles,
            "processed_updates": processed_updates,
            "executed_tasks": executed_tasks,
            "allowed_chat_id": self.telegram.allowed_chat_id,
            "last_error": last_error,
        }

    def poll_once(self) -> int:
        state = self._load_bot_state()
        updates = self.telegram.poll_updates(offset=state.get("offset"))
        processed = 0
        for update in updates:
            update_id = int(update.get("update_id"))
            state["offset"] = update_id + 1
            if update_id in state["processed_update_ids"]:
                continue
            envelope = self._build_update_envelope(update)
            if envelope is not None:
                self._handle_update(envelope)
                processed += 1
            state["processed_update_ids"].append(update_id)
            state["processed_update_ids"] = state["processed_update_ids"][-200:]
        self._save_bot_state(state)
        return processed

    def process_queue(self) -> int:
        executed = 0
        queued = self._list_tasks(statuses={"queued"})
        for task in queued:
            executed += 1
            self._execute_task(task)
        return executed

    def _handle_update(self, envelope: TelegramUpdateEnvelope) -> None:
        if not self.telegram.is_chat_allowed(envelope.chat_id):
            return

        session = self._load_session(envelope.chat_id)
        session.updated_at = envelope.received_at
        session.last_message_id = envelope.message_id
        self._save_session(session)

        command = envelope.command or ""
        if command in {"start", "help"}:
            self._send_checked_text(
                envelope.chat_id,
                self._help_text(),
                reply_to_message_id=envelope.message_id,
                fallback_text="Я на связи. Напиши /ask <задача> или /marketplace-watch.",
            )
            return
        if command == "status":
            self._send_checked_text(
                envelope.chat_id,
                self._status_text(envelope.chat_id),
                reply_to_message_id=envelope.message_id,
                fallback_text="Не смог собрать статус в красивом виде. Попробуй ещё раз через минуту.",
            )
            return
        if command == "cancel":
            self._send_checked_text(
                envelope.chat_id,
                self._cancel_latest_task(session),
                reply_to_message_id=envelope.message_id,
                fallback_text="Не смог аккуратно отменить задачу. Попробуй ещё раз.",
            )
            return
        if command == "confirm":
            self._send_checked_text(
                envelope.chat_id,
                self._confirm_pending_task(session),
                reply_to_message_id=envelope.message_id,
                fallback_text="Подтверждение принято.",
            )
            return
        if command == "reject":
            self._send_checked_text(
                envelope.chat_id,
                self._reject_pending_task(session),
                reply_to_message_id=envelope.message_id,
                fallback_text="Рискованную задачу отменил.",
            )
            return
        if command == "memory":
            self._send_checked_text(
                envelope.chat_id,
                self._memory_text(),
                reply_to_message_id=envelope.message_id,
                fallback_text="Память пока почти пустая.",
            )
            return

        request_text = self._resolve_request_text(envelope)
        task_command = "ask"
        if command == "marketplace-watch":
            task_command = "marketplace-watch"
            request_text = "Запустить marketplace watch по текущему контуру vNext."

        existing = self._find_existing_task_for_message(envelope.chat_id, envelope.message_id)
        if existing is not None:
            return

        task_id = uuid4().hex[:12]
        attachments = self._materialize_attachments(task_id, envelope.attachments)
        risky = self._is_risky_request(task_command, request_text)
        task = TaskEnvelope(
            task_id=task_id,
            source="telegram",
            command=task_command,
            request=request_text,
            chat_id=envelope.chat_id,
            message_id=envelope.message_id,
            session_id=session.session_id,
            status="awaiting_confirmation" if risky else "queued",
            attachments=attachments,
            risky=risky,
        )

        if risky:
            task.confirmation_request = ConfirmationRequest(
                confirmation_id=f"confirm-{task_id}",
                task_id=task_id,
                chat_id=envelope.chat_id,
                prompt=(
                    "Для этой задачи нужно подтверждение, потому что запрос похож на средний или высокий риск.\n"
                    "Чтобы продолжить, отправь /confirm\n"
                    "Чтобы отменить, отправь /reject"
                ),
            )
            session.pending_confirmation_id = task.confirmation_request.confirmation_id
            session.last_task_id = task.task_id
            self._save_task(task)
            self._save_session(session)
            self._send_checked_text(
                envelope.chat_id,
                task.confirmation_request.prompt,
                reply_to_message_id=envelope.message_id,
                fallback_text="Для этой задачи нужно подтверждение. Отправь /confirm или /reject.",
            )
            return

        session.last_task_id = task.task_id
        self._save_task(task)
        self._save_session(session)
        self._send_checked_text(
            envelope.chat_id,
            "Принято в работу. Финальный ответ пришлю отдельным сообщением.",
            reply_to_message_id=envelope.message_id,
            fallback_text="Принял задачу. Результат пришлю отдельным сообщением.",
        )

    def _execute_task(self, task: TaskEnvelope) -> None:
        session = self._load_session(task.chat_id)
        task.status = "running"
        task.updated_at = utc_now_iso()
        session.active_task_id = task.task_id
        self._save_task(task)
        self._save_session(session)

        try:
            if task.command == "marketplace-watch":
                envelope = self.executor.run_marketplace_watch(
                    top_limit=25,
                    sample_data=not bool(self.settings.wb_api_token),
                    headless=True,
                )
            else:
                envelope = self.executor.run_request(
                    task.request,
                    attachments=task.attachments,
                    headless=False,
                    mode="telegram",
                )
            task.status = "completed"
            task.result_summary = envelope.final_summary
            task.artifact_paths = [artifact.path for artifact in envelope.artifacts]
            task.updated_at = utc_now_iso()
            self._save_task(task)
            session.active_task_id = None
            session.last_task_id = task.task_id
            self._save_session(session)
            self._send_final_result(task, envelope)
        except Exception as exc:  # noqa: BLE001
            task.status = "failed"
            task.error = str(exc)
            task.updated_at = utc_now_iso()
            self._save_task(task)
            session.active_task_id = None
            session.last_task_id = task.task_id
            self._save_session(session)
            self._send_checked_text(
                task.chat_id,
                (
                    "Задача завершилась с ошибкой.\n"
                    f"Что пытался сделать: {task.request[:180]}\n"
                    f"Ошибка: {str(exc)[:500]}"
                ),
                reply_to_message_id=task.message_id,
                fallback_text="Задача завершилась с ошибкой. Если хочешь, я переформулирую проблему следующим сообщением.",
            )

    def _send_final_result(self, task: TaskEnvelope, envelope: RunEnvelope) -> None:
        final_text = self._compose_user_facing_reply(task, envelope)
        self._send_checked_text(
            task.chat_id,
            final_text,
            reply_to_message_id=task.message_id,
            fallback_text="Готово. Результат подготовил в более безопасном и коротком виде.",
        )
        for artifact_path in self._select_artifacts_for_delivery(task, envelope):
            self.telegram.send_file_to_chat(
                task.chat_id,
                artifact_path,
                caption=f"Артефакт по задаче {task.task_id}",
                reply_to_message_id=task.message_id,
            )

    def _compose_user_facing_reply(self, task: TaskEnvelope, envelope: RunEnvelope) -> str:
        if envelope.user_message:
            base = envelope.user_message.strip()
        elif task.command == "marketplace-watch":
            base = "Собрал свежий marketplace watch. Основной результат отправил отдельным файлом."
        else:
            base = "Готово. Запрос обработал."
        if task.command == "marketplace-watch":
            return base
        if envelope.alerts:
            return f"{base}\n\nЕсть ограничения по материалам. Если хочешь, следующим сообщением уточню их коротко."
        return base

    def _select_artifacts_for_delivery(self, task: TaskEnvelope, envelope: RunEnvelope) -> list[str]:
        if task.command == "marketplace-watch":
            preferred = ["html", "markdown", "xlsx"]
        elif task.attachments:
            preferred = ["markdown"]
        else:
            preferred = []
        selected: list[str] = []
        for kind in preferred:
            for artifact in envelope.artifacts:
                if artifact.kind == kind and artifact.path not in selected:
                    selected.append(artifact.path)
                    break
        return selected[:3]

    def _send_checked_text(
        self,
        chat_id: str,
        text: str,
        *,
        reply_to_message_id: int | None = None,
        fallback_text: str,
    ) -> None:
        if self._looks_broken_or_internal(text):
            self.memory.append_daily_log(
                "Telegram outgoing text blocked",
                f"Blocked message for chat {chat_id}: {text[:400]}",
            )
            safe_text = fallback_text
        else:
            safe_text = text
        self.telegram.send_text_to_chat(
            chat_id,
            safe_text,
            reply_to_message_id=reply_to_message_id,
        )

    def _looks_broken_or_internal(self, text: str) -> bool:
        if not text or not text.strip():
            return True
        forbidden_fragments = (
            "Что сделал:",
            "Текущее состояние:",
            "Итоговая сводка сохранена:",
            "Ролей в маршруте:",
            "Вложений:",
            "task_id",
            ".agent_codex\\artifacts",
        )
        if any(fragment in text for fragment in forbidden_fragments):
            return True
        mojibake_markers = ("РџС", "С‚Р", "РёС", "СЏ", "Р°Р", "РЅР", "СЃС", "РћС", "Р•С")
        if sum(text.count(marker) for marker in mojibake_markers) >= 2:
            return True
        weird_chars = "ЃѓЉЌЋЏђ‘’“”•™љ›њќћџ"
        if any(char in text for char in weird_chars):
            return True
        return False

    def _resolve_request_text(self, envelope: TelegramUpdateEnvelope) -> str:
        if envelope.command == "ask":
            return (envelope.command_args or "").strip() or "Проанализировать присланные материалы."
        if envelope.text.strip():
            return envelope.text.strip()
        if envelope.caption:
            return envelope.caption.strip()
        if envelope.attachments:
            return "Проанализировать присланные материалы."
        return "Помочь с новой задачей из Telegram."

    def _materialize_attachments(self, task_id: str, attachments: list[TelegramAttachment]) -> list[TelegramAttachment]:
        materialized: list[TelegramAttachment] = []
        for item in attachments:
            cloned = TelegramAttachment(
                kind=item.kind,
                file_id=item.file_id,
                file_name=item.file_name,
                mime_type=item.mime_type,
                size_bytes=item.size_bytes,
                local_path=item.local_path,
            )
            destination = self._attachment_destination(task_id, cloned)
            try:
                cloned.local_path = str(self.telegram.download_file(cloned.file_id, destination))
            except TelegramNotifyError as exc:
                cloned.local_path = None
                cloned.file_name = cloned.file_name or destination.name
                cloned.mime_type = cloned.mime_type or "application/octet-stream"
                self.memory.append_daily_log(
                    "Telegram attachment download issue",
                    f"Не удалось скачать {cloned.file_name or cloned.file_id}: {exc}",
                )
            materialized.append(cloned)
        return materialized

    def _attachment_destination(self, task_id: str, attachment: TelegramAttachment) -> Path:
        base_dir = self.settings.telegram_inbox_root / task_id
        base_dir.mkdir(parents=True, exist_ok=True)
        file_name = self._safe_attachment_name(attachment)
        return base_dir / file_name

    def _safe_attachment_name(self, attachment: TelegramAttachment) -> str:
        original = attachment.file_name or f"{attachment.kind}_{attachment.file_id}"
        original = re.sub(r"[^a-zA-Z0-9._-]+", "_", original)
        suffix = Path(original).suffix
        if suffix:
            return original
        guessed_extension = mimetypes.guess_extension(attachment.mime_type or "") or ""
        if attachment.kind == "photo" and not guessed_extension:
            guessed_extension = ".jpg"
        return f"{original}{guessed_extension}"

    def _build_update_envelope(self, update: dict) -> TelegramUpdateEnvelope | None:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return None
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        message_id = message.get("message_id")
        if chat_id is None or message_id is None:
            return None

        text = str(message.get("text") or "")
        caption = message.get("caption")
        command = None
        command_args = None
        if text.startswith("/"):
            parts = text.split(maxsplit=1)
            raw_command = parts[0][1:]
            command = raw_command.split("@", 1)[0].strip().lower()
            command_args = parts[1].strip() if len(parts) > 1 else None

        attachments: list[TelegramAttachment] = []
        document = message.get("document")
        if isinstance(document, dict):
            attachments.append(
                TelegramAttachment(
                    kind="document",
                    file_id=str(document.get("file_id") or ""),
                    file_name=document.get("file_name"),
                    mime_type=document.get("mime_type"),
                    size_bytes=document.get("file_size"),
                )
            )
        photo_list = message.get("photo") or []
        if isinstance(photo_list, list) and photo_list:
            photo = sorted(photo_list, key=lambda item: int(item.get("file_size") or 0))[-1]
            attachments.append(
                TelegramAttachment(
                    kind="photo",
                    file_id=str(photo.get("file_id") or ""),
                    file_name=f"photo_{message_id}.jpg",
                    mime_type="image/jpeg",
                    size_bytes=photo.get("file_size"),
                )
            )

        return TelegramUpdateEnvelope(
            update_id=int(update.get("update_id")),
            chat_id=str(chat_id),
            message_id=int(message_id),
            text=text,
            command=command,
            command_args=command_args,
            caption=caption,
            attachments=attachments,
            reply_to_message_id=((message.get("reply_to_message") or {}).get("message_id")),
        )

    def _load_bot_state(self) -> dict:
        if not self.state_path.exists():
            return {"offset": None, "processed_update_ids": []}
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        return {
            "offset": data.get("offset"),
            "processed_update_ids": list(data.get("processed_update_ids") or []),
        }

    def _save_bot_state(self, state: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_session(self, chat_id: str) -> TelegramConversationSession:
        path = self.telegram_sessions_root / f"{chat_id}.json"
        if not path.exists():
            now = utc_now_iso()
            session = TelegramConversationSession(
                session_id=f"telegram-{chat_id}",
                chat_id=chat_id,
                created_at=now,
                updated_at=now,
            )
            self._save_session(session)
            return session
        data = json.loads(path.read_text(encoding="utf-8"))
        return TelegramConversationSession(**data)

    def _save_session(self, session: TelegramConversationSession) -> None:
        path = self.telegram_sessions_root / f"{session.chat_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(session), ensure_ascii=False, indent=2), encoding="utf-8")

    def _task_path(self, task_id: str) -> Path:
        return self.tasks_root / f"telegram_{task_id}.json"

    def _save_task(self, task: TaskEnvelope) -> None:
        payload = asdict(task)
        self._task_path(task.task_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_task(self, task_id: str) -> TaskEnvelope | None:
        path = self._task_path(task_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        attachments = [TelegramAttachment(**item) for item in data.get("attachments", [])]
        confirmation_payload = data.get("confirmation_request")
        confirmation = ConfirmationRequest(**confirmation_payload) if confirmation_payload else None
        return TaskEnvelope(
            task_id=data["task_id"],
            source=data["source"],
            command=data["command"],
            request=data["request"],
            chat_id=data["chat_id"],
            message_id=int(data["message_id"]),
            session_id=data["session_id"],
            status=data["status"],
            attachments=attachments,
            risky=bool(data.get("risky")),
            confirmation_request=confirmation,
            result_summary=data.get("result_summary"),
            artifact_paths=list(data.get("artifact_paths") or []),
            error=data.get("error"),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    def _list_tasks(self, *, chat_id: str | None = None, statuses: set[str] | None = None) -> list[TaskEnvelope]:
        tasks: list[TaskEnvelope] = []
        for path in sorted(self.tasks_root.glob("telegram_*.json")):
            task = self._load_task(path.stem.replace("telegram_", "", 1))
            if task is None:
                continue
            if chat_id is not None and task.chat_id != chat_id:
                continue
            if statuses is not None and task.status not in statuses:
                continue
            tasks.append(task)
        tasks.sort(key=lambda item: item.created_at)
        return tasks

    def _find_existing_task_for_message(self, chat_id: str, message_id: int) -> TaskEnvelope | None:
        for task in self._list_tasks(chat_id=chat_id):
            if int(task.message_id) == int(message_id) and task.status != "failed":
                return task
        return None

    def _status_text(self, chat_id: str) -> str:
        tasks = self._list_tasks(chat_id=chat_id)
        if not tasks:
            return "Активных задач пока нет."
        latest = tasks[-5:]
        lines = ["Последние задачи:"]
        for task in latest:
            lines.append(f"- {task.task_id}: {task.status} — {task.request[:80]}")
        return "\n".join(lines)

    def _cancel_latest_task(self, session: TelegramConversationSession) -> str:
        if session.pending_confirmation_id:
            task = self._find_task_by_confirmation(session.pending_confirmation_id)
            if task:
                task.status = "cancelled"
                task.updated_at = utc_now_iso()
                self._save_task(task)
                session.pending_confirmation_id = None
                self._save_session(session)
                return f"Отменил задачу {task.task_id} до запуска."
        queued = [item for item in self._list_tasks(chat_id=session.chat_id, statuses={"queued"})]
        if queued:
            task = queued[-1]
            task.status = "cancelled"
            task.updated_at = utc_now_iso()
            self._save_task(task)
            return f"Отменил задачу {task.task_id} из очереди."
        if session.active_task_id:
            return (
                "Сейчас задача уже выполняется. Для первой версии бота отмена доступна только до запуска "
                "или на стадии подтверждения."
            )
        return "Отменять пока нечего."

    def _confirm_pending_task(self, session: TelegramConversationSession) -> str:
        if not session.pending_confirmation_id:
            return "Нет задач, ожидающих подтверждения."
        task = self._find_task_by_confirmation(session.pending_confirmation_id)
        if not task:
            session.pending_confirmation_id = None
            self._save_session(session)
            return "Подтверждение больше не нужно: задача уже исчезла из очереди."
        if task.confirmation_request:
            task.confirmation_request.status = "confirmed"
            task.confirmation_request.updated_at = utc_now_iso()
        task.status = "queued"
        task.updated_at = utc_now_iso()
        self._save_task(task)
        session.pending_confirmation_id = None
        self._save_session(session)
        return f"Подтверждение принято. Задача {task.task_id} поставлена в очередь."

    def _reject_pending_task(self, session: TelegramConversationSession) -> str:
        if not session.pending_confirmation_id:
            return "Нет задач, ожидающих подтверждения."
        task = self._find_task_by_confirmation(session.pending_confirmation_id)
        if not task:
            session.pending_confirmation_id = None
            self._save_session(session)
            return "Подтверждение уже не требуется."
        if task.confirmation_request:
            task.confirmation_request.status = "rejected"
            task.confirmation_request.updated_at = utc_now_iso()
        task.status = "cancelled"
        task.updated_at = utc_now_iso()
        self._save_task(task)
        session.pending_confirmation_id = None
        self._save_session(session)
        return f"Задача {task.task_id} отменена по отклонённому подтверждению."

    def _find_task_by_confirmation(self, confirmation_id: str) -> TaskEnvelope | None:
        for task in self._list_tasks():
            if task.confirmation_request and task.confirmation_request.confirmation_id == confirmation_id:
                return task
        return None

    def _memory_text(self) -> str:
        entries = self.memory.load_index()[:5]
        if not entries:
            return "Память пока почти пустая."
        lines = ["Последние темы памяти:"]
        for item in entries:
            lines.append(f"- {item.title}")
        return "\n".join(lines)

    def _help_text(self) -> str:
        return (
            "Я подключён к Agent_Codex vNext.\n"
            "Команды первой версии:\n"
            "/ask <задача> — свободный запрос\n"
            "/marketplace-watch — собрать marketplace watch\n"
            "/memory — показать память\n"
            "/status — статус последних задач\n"
            "/cancel — отменить ещё не запущенную задачу\n"
            "/confirm — подтвердить рискованную задачу\n"
            "/reject — отклонить рискованную задачу"
        )

    def _is_risky_request(self, command: str, request: str) -> bool:
        if command in {"marketplace-watch", "memory"}:
            return False
        lowered = request.lower()
        risky_markers = (
            "удали",
            "удалить",
            "сотри",
            "перемести",
            "переименуй",
            "измени файл",
            "запиши",
            "сделай коммит",
            "push",
            "git push",
            "git commit",
            "установи",
            "install",
            "shutdown",
            "sleep",
            "reboot",
            "service",
            "powershell",
            "cmd ",
            "rm ",
            "del ",
            "format ",
        )
        return any(marker in lowered for marker in risky_markers)
