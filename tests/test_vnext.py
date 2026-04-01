from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_codex.apps.cli.main import main
from agent_codex.config import ensure_runtime_layout, load_settings
from agent_codex.domains.marketplace.artifacts import (
    render_watch_dashboard_html,
    render_watch_summary_markdown,
)
from agent_codex.hooks.policy import evaluate_tool_action
from agent_codex.hooks import HookPipeline
from agent_codex.memory import ConsolidationEngine, MemoryStore
from agent_codex.runtime import AgentExecutor, Coordinator


class VNextTests(unittest.TestCase):
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
            settings = load_settings(tmp)
            ensure_runtime_layout(settings)
            executor = AgentExecutor(
                settings=settings,
                coordinator=Coordinator(),
                hooks=HookPipeline(settings),
                memory=MemoryStore(settings),
            )
            envelope = executor.run_marketplace_watch(top_limit=10, sample_data=True, headless=True)
            self.assertTrue(envelope.final_summary)
            self.assertTrue(any(item.kind == "html" for item in envelope.artifacts))
            self.assertTrue(any("marketplace_analyst" in line for line in envelope.task_graph))

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


if __name__ == "__main__":
    unittest.main()
