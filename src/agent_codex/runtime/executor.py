from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

from ..commands import COMMANDS
from ..config import Settings
from ..contracts import RunEnvelope, WorkerContext, WorkerResult
from ..domains.marketplace.service import MarketplaceService
from ..hooks import HookPipeline
from ..integrations.llm import select_backend
from ..memory import ConsolidationEngine, MemoryStore
from ..skills import list_bundled_skills
from .coordinator import Coordinator


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

    def doctor_report(self) -> dict:
        return {
            "project_root": str(self.settings.project_root),
            "runtime_root": str(self.settings.runtime_root),
            "telegram_configured": bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id),
            "wb_configured": bool(self.settings.wb_api_token),
            "skills": ", ".join(list_bundled_skills(self.settings.project_root)),
            "commands": ", ".join(item.name for item in COMMANDS),
            "backends": f"primary={self.settings.primary_reasoning_backend}, background={self.settings.background_backend}, cheap={self.settings.cheap_backend}",
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

    def run_marketplace_watch(self, *, top_limit: int, sample_data: bool, headless: bool) -> RunEnvelope:
        run_id = uuid4().hex
        request = "Marketplace cabinet watch"
        self.hooks.pre_task(request, mode="headless" if headless else "interactive")
        self.memory.write_session_event({"run_id": run_id, "request": request, "mode": "headless" if headless else "interactive"})
        ConsolidationEngine(self.settings).record_session_event()

        task_graph = self.coordinator.build_task_graph(request, domain="marketplace")
        context = WorkerContext(
            run_id=run_id,
            request=request,
            mode="headless" if headless else "interactive",
            selected_roles=[task.role for task in task_graph.tasks],
            project_root=str(self.settings.project_root),
            runtime_root=str(self.settings.runtime_root),
            scratchpad_root=str(self.settings.runtime_root / "scratchpad"),
        )
        backend = select_backend(self.settings.background_backend if headless else self.settings.primary_reasoning_backend)

        monitor_result, artifacts = self.marketplace.run_watch(top_limit=top_limit, sample_data=sample_data)
        worker_results: list[WorkerResult] = []
        for task in task_graph.tasks:
            response = backend.run(task, context)
            worker_results.append(
                WorkerResult(
                    task_id=task.id,
                    role=task.role,
                    status="completed",
                    summary=response.summary,
                    output=response.output,
                    evidence=[f"artifact:{artifacts.dashboard_html.path}", f"rows:{monitor_result.row_count}"],
                )
            )
        final_summary = (
            f"Построен marketplace watch. SKU в мониторинге: {monitor_result.row_count}. "
            f"Основной артефакт: {artifacts.dashboard_html.path}."
        )
        envelope = RunEnvelope(
            run_id=run_id,
            request=request,
            mode=context.mode,
            task_graph=task_graph.summarize(),
            results=worker_results,
            artifacts=[
                artifacts.markdown,
                artifacts.summary_markdown,
                artifacts.dashboard_html,
                artifacts.workbook,
            ],
            final_summary=final_summary,
            alerts=[],
        )
        self.hooks.pre_reply(final_summary)
        self.hooks.post_run(envelope)
        self.memory.append_daily_log(
            "Marketplace watch run",
            f"{final_summary}\n\nArtifacts:\n- {artifacts.dashboard_html.path}\n- {artifacts.markdown.path}",
        )
        return envelope
