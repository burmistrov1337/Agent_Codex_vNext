from __future__ import annotations

import importlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..commands import COMMANDS
from ..config import Settings
from ..contracts import (
    RunEnvelope,
    SynthesisInput,
    TelegramAttachment,
    WorkerContext,
    WorkerResult,
    artifact_from_path,
)
from ..domains.marketplace.service import MarketplaceService
from ..hooks import HookPipeline
from ..integrations.llm import select_backend
from ..memory import ConsolidationEngine, MemoryStore
from ..skills import list_bundled_skills
from .coordinator import Coordinator
from .metrics import RuntimeMetricsCollector
from .synthesizer import Synthesizer


class AgentExecutor:
    def __init__(
        self,
        *,
        settings: Settings,
        coordinator: Coordinator,
        hooks: HookPipeline,
        memory: MemoryStore,
    ) -> None:
        self.settings = settings
        self.coordinator = coordinator
        self.hooks = hooks
        self.memory = memory
        self.marketplace = MarketplaceService(settings)
        self.synthesizer = Synthesizer()

    def doctor_report(self) -> dict:
        sales_state = self._sales_surface_state()
        return {
            "project_root": str(self.settings.project_root),
            "runtime_root": str(self.settings.runtime_root),
            "config_issues": self.settings.validate(),
            "telegram_configured": bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id),
            "wb_configured": bool(self.settings.wb_api_token),
            "sales_artifact_root": str(self.settings.sales_artifact_root),
            "sales_sheet_configured": bool(self.settings.google_sheets_spreadsheet_id),
            "google_service_account_configured": bool(
                self.settings.google_service_account_file or self.settings.google_service_account_json
            ),
            "advantshop_configured": bool(self.settings.advantshop_api_url and (self.settings.advantshop_api or self.settings.advantshop_api_auth)),
            "sales_sheet_refresh_cron": self.settings.sales_sheet_refresh_cron,
            "sales_sheet_surface": sales_state["state"],
            "sales_sheet_surface_message": sales_state["message"],
            "skills": ", ".join(list_bundled_skills(self.settings.project_root)),
            "commands": ", ".join(item.name for item in COMMANDS),
            "backends": (
                f"primary={self.settings.primary_reasoning_backend}, "
                f"background={self.settings.background_backend}, "
                f"cheap={self.settings.cheap_backend}"
            ),
        }

    def memory_report(self, *, run_consolidation: bool = False) -> dict:
        report = {
            "index_entries": len(self.memory.load_index()),
            "memory_index": str(self.memory.index_path),
        }
        engine = ConsolidationEngine(self.settings)
        if run_consolidation:
            report["consolidation"] = engine.run()
        else:
            report["consolidation_ready"] = engine.should_run()
        return report

    def metrics_report(self) -> dict:
        collector = RuntimeMetricsCollector(self.settings, self.memory)
        return collector.collect()

    def review_report(self, text: str) -> dict:
        violations = self.coordinator.validate_synthesis(text)
        return {
            "violations": violations,
            "is_clean": not violations,
        }

    def tasks_report(self) -> dict:
        task_dir = self.settings.runtime_root / "tasks"
        tasks = sorted(path.name for path in task_dir.glob("*") if path.is_file())
        return {"task_files": tasks, "task_dir": str(task_dir)}

    def hooks_report(self, *, tool_name: str, path: str | None) -> dict:
        decision = self.hooks.pre_tool(tool_name, target_path=path)
        return asdict(decision)

    def compact_report(self, text: str) -> dict:
        cleaned = " ".join((text or "").split())
        parts = [segment.strip() for segment in cleaned.split(".") if segment.strip()]
        summary = ". ".join(parts[:3])
        return {"summary": summary or cleaned[:280], "source_length": len(cleaned)}

    def study_digest_report(self, path: str | None) -> dict:
        if not path:
            return {"error": "input path is required"}
        file_path = self.settings.project_root / path
        if not file_path.exists():
            file_path = file_path.resolve()
        text = file_path.read_text(encoding="utf-8", errors="replace")
        paragraphs = [item.strip() for item in text.splitlines() if item.strip()]
        digest = paragraphs[:8]
        artifact_dir = self.settings.runtime_root / "artifacts" / "study"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        digest_path = artifact_dir / f"{file_path.stem}_digest.md"
        digest_path.write_text("# Study Digest\n\n" + "\n\n".join(f"- {item}" for item in digest), encoding="utf-8")
        return {"digest_path": str(digest_path), "points": len(digest)}

    def sales_sheet_init_report(self) -> dict[str, Any]:
        return self._sales_command_report("init")

    def sales_sheet_refresh_report(self, *, scope: str = "all") -> dict[str, Any]:
        if scope not in {"all", "wb", "site"}:
            return {
                "status": "error",
                "command": "sales-sheet-refresh",
                "scope": scope,
                "message": "scope must be one of: all, wb, site",
            }
        return self._sales_command_report("refresh", scope=scope)

    def sales_sheet_diagnose_report(self) -> dict[str, Any]:
        return self._sales_command_report("diagnose")

    def _sales_command_report(self, action: str, *, scope: str | None = None) -> dict[str, Any]:
        state = self._sales_surface_state()
        payload: dict[str, Any] = {
            "command": f"sales-sheet-{action}",
            "status": state["state"],
            "message": state["message"],
            "sales_artifact_root": str(self.settings.sales_artifact_root),
            "google_sheets_spreadsheet_id": self.settings.google_sheets_spreadsheet_id,
            "google_service_account_configured": bool(
                self.settings.google_service_account_file or self.settings.google_service_account_json
            ),
            "advantshop_configured": bool(
                self.settings.advantshop_api_url and (self.settings.advantshop_api or self.settings.advantshop_api_auth)
            ),
            "sales_sheet_refresh_cron": self.settings.sales_sheet_refresh_cron,
            "sales_surface_available": state["available"],
        }
        if scope is not None:
            payload["scope"] = scope
        if state["available"]:
            try:
                service = self._build_sales_service()
                runner = {
                    "init": service.init_workbook,
                    "refresh": lambda: service.refresh(scope=scope or "all"),
                    "diagnose": service.diagnose,
                }[action]
                result = runner()
                payload.update(result if isinstance(result, dict) else {"result": result})
                payload["status"] = payload.get("status", "ok")
                return payload
            except Exception as exc:
                payload["status"] = "error"
                payload["message"] = str(exc)
                payload["error"] = exc.__class__.__name__
                return payload
        payload["next_step"] = (
            "Add the sales domain service layer under src/agent_codex/domains/sales/service.py."
        )
        return payload

    def _sales_surface_state(self) -> dict[str, Any]:
        try:
            importlib.import_module("agent_codex.domains.sales.service")
        except ModuleNotFoundError:
            return {
                "available": False,
                "state": "warning",
                "message": "sales domain service is not available yet",
            }
        except Exception as exc:
            return {
                "available": False,
                "state": "error",
                "message": f"sales domain import failed: {exc}",
            }
        return {
            "available": True,
            "state": "ok",
            "message": "sales domain service is available",
        }

    def _build_sales_service(self):
        module = importlib.import_module("agent_codex.domains.sales.service")
        service_cls = getattr(module, "SalesSheetService", None)
        if service_cls is None:
            raise RuntimeError("SalesSheetService is not defined in agent_codex.domains.sales.service")
        return service_cls(self.settings)

    def run_request(
        self,
        request: str,
        *,
        attachments: list[TelegramAttachment] | None = None,
        headless: bool = False,
        mode: str = "interactive",
    ) -> RunEnvelope:
        run_id = uuid4().hex
        normalized_request = (request or "").strip() or "Проанализировать присланные материалы."
        attachments = attachments or []
        attachment_notes, attachment_limitations = self._collect_attachment_notes(attachments)

        effective_request = normalized_request
        if attachments:
            attachment_lines = []
            for item in attachments:
                label = item.file_name or Path(item.local_path or item.file_id).name
                attachment_lines.append(f"- {item.kind}: {label}")
            effective_request = f"{normalized_request}\n\nКонтекст вложений:\n" + "\n".join(attachment_lines)

        self.hooks.pre_task(effective_request, mode=mode)
        self.memory.write_session_event({"run_id": run_id, "request": effective_request, "mode": mode})
        ConsolidationEngine(self.settings).record_session_event()

        task_graph = self.coordinator.build_task_graph(effective_request)
        context = WorkerContext(
            run_id=run_id,
            request=effective_request,
            mode=mode,
            selected_roles=[task.role for task in task_graph.tasks],
            project_root=str(self.settings.project_root),
            runtime_root=str(self.settings.runtime_root),
            scratchpad_root=str(self.settings.runtime_root / "scratchpad"),
        )
        worker_results = self._execute_workers(
            task_graph=task_graph,
            context=context,
            headless=headless,
            attachments=attachments,
            attachment_notes=attachment_notes,
            attachment_limitations=attachment_limitations,
        )

        artifact_dir = self.settings.runtime_root / "artifacts" / "runs" / run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        summary_path = artifact_dir / "telegram_request_summary.md"
        summary_lines = [
            "# Telegram Request Summary",
            "",
            f"- Request: {normalized_request}",
            f"- Mode: {mode}",
            f"- Roles: {', '.join(context.selected_roles)}",
            f"- Attachments: {len(attachments)}",
            "",
            "## Worker Summaries",
            "",
        ]
        summary_lines.extend(f"- {item.role}: {item.summary}" for item in worker_results)
        if attachment_notes:
            summary_lines.extend(["", "## Attachment Notes", ""])
            summary_lines.extend(f"- {item}" for item in attachment_notes)
        if attachment_limitations:
            summary_lines.extend(["", "## Limitations", ""])
            summary_lines.extend(f"- {item}" for item in attachment_limitations)
        summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

        artifacts = [artifact_from_path(summary_path, "markdown", "Telegram request summary")]
        synthesis = self.synthesizer.synthesize(
            SynthesisInput(
                request=normalized_request,
                mode=context.mode,
                task_graph=task_graph.summarize(),
                worker_results=worker_results,
                artifacts=artifacts,
                alerts=attachment_limitations[:],
            )
        )
        synthesis = self.coordinator.decide_continuation(worker_results, synthesis)

        user_message = self._build_user_message(
            normalized_request,
            attachments=attachments,
            has_limitations=bool(attachment_limitations),
            synthesis_message=synthesis.user_message,
        )
        envelope = RunEnvelope(
            run_id=run_id,
            request=normalized_request,
            mode=context.mode,
            task_graph=task_graph.summarize(),
            results=worker_results,
            artifacts=artifacts,
            final_summary=synthesis.final_summary,
            alerts=attachment_limitations[:],
            user_message=user_message,
            synthesis=synthesis,
        )
        envelope_path = self._persist_run_envelope(envelope, artifact_dir)
        self.hooks.pre_reply(envelope.final_summary)
        self.hooks.post_run(envelope)
        self.memory.append_daily_log(
            "Generic request run",
            f"{envelope.final_summary}\n\nSummary artifact:\n- {summary_path}\n- Run envelope: {envelope_path}",
        )
        return envelope

    def run_marketplace_watch(self, *, top_limit: int, sample_data: bool, headless: bool) -> RunEnvelope:
        run_id = uuid4().hex
        request = "Marketplace cabinet watch"
        mode = "headless" if headless else "interactive"
        self.hooks.pre_task(request, mode=mode)
        self.memory.write_session_event({"run_id": run_id, "request": request, "mode": mode})
        ConsolidationEngine(self.settings).record_session_event()

        task_graph = self.coordinator.build_task_graph(request, domain="marketplace")
        context = WorkerContext(
            run_id=run_id,
            request=request,
            mode=mode,
            selected_roles=[task.role for task in task_graph.tasks],
            project_root=str(self.settings.project_root),
            runtime_root=str(self.settings.runtime_root),
            scratchpad_root=str(self.settings.runtime_root / "scratchpad"),
        )

        monitor_result, monitor_artifacts = self.marketplace.run_watch(top_limit=top_limit, sample_data=sample_data)
        worker_results = self._execute_workers(task_graph=task_graph, context=context, headless=headless)
        artifacts = [
            monitor_artifacts.markdown,
            monitor_artifacts.summary_markdown,
            monitor_artifacts.dashboard_html,
            monitor_artifacts.workbook,
        ]
        synthesis = self.synthesizer.synthesize(
            SynthesisInput(
                request=request,
                mode=context.mode,
                task_graph=task_graph.summarize(),
                worker_results=worker_results,
                artifacts=artifacts,
                alerts=[],
            )
        )
        synthesis = self.coordinator.decide_continuation(worker_results, synthesis)
        final_summary = (
            f"{synthesis.final_summary} SKU в мониторинге: {monitor_result.row_count}. "
            f"Основной артефакт: {monitor_artifacts.dashboard_html.path}."
        )
        envelope = RunEnvelope(
            run_id=run_id,
            request=request,
            mode=context.mode,
            task_graph=task_graph.summarize(),
            results=worker_results,
            artifacts=artifacts,
            final_summary=final_summary,
            alerts=[],
            user_message=(
                f"Собрал свежий marketplace watch. В мониторинге {monitor_result.row_count} SKU. "
                "Основной результат отправил отдельным файлом."
            ),
            synthesis=synthesis,
        )
        artifact_dir = self.settings.runtime_root / "artifacts" / "runs" / run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        envelope_path = self._persist_run_envelope(envelope, artifact_dir)
        self.hooks.pre_reply(envelope.final_summary)
        self.hooks.post_run(envelope)
        self.memory.append_daily_log(
            "Marketplace watch run",
            f"{envelope.final_summary}\n\nArtifacts:\n- {monitor_artifacts.dashboard_html.path}\n- {monitor_artifacts.markdown.path}\n- Run envelope: {envelope_path}",
        )
        return envelope

    def _execute_workers(
        self,
        *,
        task_graph,
        context: WorkerContext,
        headless: bool,
        attachments: list[TelegramAttachment] | None = None,
        attachment_notes: list[str] | None = None,
        attachment_limitations: list[str] | None = None,
    ) -> list[WorkerResult]:
        attachments = attachments or []
        attachment_notes = attachment_notes or []
        attachment_limitations = attachment_limitations or []
        backend = select_backend(
            self.settings.background_backend if headless else self.settings.primary_reasoning_backend,
            groq_api_key=self.settings.groq_api_key,
            groq_model=self.settings.groq_model,
            openai_api_key=self.settings.openai_api_key,
            openai_model=self.settings.openai_model,
            anthropic_api_key=self.settings.anthropic_api_key,
            anthropic_model=self.settings.anthropic_model,
            ollama_base_url=self.settings.ollama_base_url,
            ollama_model=self.settings.ollama_model,
        )
        evidence = [f"attachment:{item.local_path or item.file_name or item.file_id}" for item in attachments]
        evidence.extend(attachment_notes[:3])
        evidence.extend(f"limitation:{item}" for item in attachment_limitations[:2])

        worker_results: list[WorkerResult] = []
        for task in task_graph.tasks:
            response = backend.run(task, context)
            output = response.output
            if attachment_notes:
                output = output + "\n\nИзвлечённые заметки по вложениям:\n" + "\n".join(f"- {item}" for item in attachment_notes)
            if attachment_limitations:
                output = output + "\n\nОграничения:\n" + "\n".join(f"- {item}" for item in attachment_limitations)
            worker_results.append(
                WorkerResult(
                    task_id=task.id,
                    role=task.role,
                    status="completed",
                    summary=response.summary,
                    output=output,
                    evidence=evidence,
                    gaps=list(response.gaps or []),
                    follow_up_actions=list(response.follow_up_actions or []),
                )
            )
        return worker_results

    def _persist_run_envelope(self, envelope: RunEnvelope, artifact_dir: Path) -> Path:
        envelope_path = artifact_dir / "run_envelope.json"
        envelope_path.write_text(json.dumps(envelope.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return envelope_path

    def _collect_attachment_notes(self, attachments: list[TelegramAttachment]) -> tuple[list[str], list[str]]:
        notes: list[str] = []
        limitations: list[str] = []
        for item in attachments:
            if not item.local_path:
                limitations.append(f"Вложение {item.file_name or item.file_id} ещё не скачано в runtime inbox.")
                continue
            path = Path(item.local_path)
            if not path.exists():
                limitations.append(f"Вложение {path.name} не найдено на диске после загрузки.")
                continue
            suffix = path.suffix.lower()
            if suffix in {".txt", ".md"}:
                text = path.read_text(encoding="utf-8", errors="replace").strip()
                if text:
                    notes.append(f"{path.name}: {text[:400].replace(chr(10), ' ')}")
                else:
                    limitations.append(f"Вложение {path.name} пустое.")
                continue
            limitations.append(
                f"Автоматическое извлечение содержимого из {path.name} ({item.kind}) пока не реализовано; файл сохранён для последующей обработки."
            )
        return notes, limitations

    def _build_user_message(
        self,
        request: str,
        *,
        attachments: list[TelegramAttachment],
        has_limitations: bool,
        synthesis_message: str | None = None,
    ) -> str:
        normalized = " ".join((request or "").strip().split())
        lowered = normalized.lower()
        short = re.sub(r"\s+", " ", lowered).strip("!?., ")

        if short in {"привет", "здравствуй", "здравствуйте", "добрый день", "добрый вечер"}:
            return "Привет. Я на связи."
        if short in {"ты здесь", "ты тут", "ответь", "ты работаешь"}:
            return "Да, я на связи и готов работать."
        if short in {"спасибо", "благодарю"}:
            return "Пожалуйста. Если хочешь, можем сразу продолжить."
        if attachments and has_limitations:
            return (
                "Материалы получил. Часть файлов сохранил, но не всё смог разобрать автоматически. "
                "Если хочешь, следующим сообщением скажу, что лучше прислать или в каком виде."
            )
        if attachments:
            return "Материалы получил и подготовил краткий результат. Если нужно, могу углубить разбор."
        if synthesis_message and synthesis_message.strip():
            return synthesis_message.strip()
        if normalized.endswith("?"):
            return "Готово. Короткий ответ подготовил. Если хочешь, могу раскрыть тему подробнее."
        return "Готово. Запрос обработал. Если хочешь, следующим сообщением продолжу уже по сути задачи."
