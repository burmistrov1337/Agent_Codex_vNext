from __future__ import annotations

import argparse
import json
import logging

from ...commands import COMMANDS
from ...config import ensure_runtime_layout, load_settings
from ...hooks import HookPipeline
from ...integrations.n8n import build_n8n_payload
from ...integrations.telegram import TelegramAdapter
from ...logging_config import setup_logging
from ...memory import MemoryStore
from ...runtime import AgentExecutor, Coordinator, TaskBus, TaskBusMaintainer, TelegramBotService


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent_codex_vnext")
    parser.add_argument("command", choices=[spec.name for spec in COMMANDS])
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--input")
    parser.add_argument("--sample-data", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--notify-telegram", action="store_true")
    parser.add_argument("--top-limit", type=int, default=25)
    parser.add_argument("--scope", choices=["all", "wb", "site"], default="all")
    parser.add_argument("--path")
    parser.add_argument("--tool", default="shell")
    parser.add_argument("--run-consolidation", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-cycles", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.project_root)
    ensure_runtime_layout(settings)
    setup_logging(log_file=settings.runtime_root / "agent.log")
    LOGGER.debug("CLI initialized", extra={"run_id": None})
    memory = MemoryStore(settings)
    hooks = HookPipeline(settings)
    coordinator = Coordinator()
    executor = AgentExecutor(settings=settings, coordinator=coordinator, hooks=hooks, memory=memory)
    telegram = TelegramAdapter(settings)
    telegram_bot = TelegramBotService(settings=settings, executor=executor, telegram=telegram, memory=memory)
    task_bus = TaskBus(settings.runtime_root / "tasks")
    maintainer = TaskBusMaintainer(task_bus)

    if args.command == "doctor":
        payload = executor.doctor_report()
        return _emit(payload, as_json=args.json)
    if args.command == "metrics":
        payload = executor.metrics_report()
        return _emit(payload, as_json=True if args.json else False)
    if args.command == "memory":
        payload = executor.memory_report(run_consolidation=args.run_consolidation)
        return _emit(payload, as_json=args.json)
    if args.command == "review":
        payload = executor.review_report(args.input or "")
        return _emit(payload, as_json=args.json)
    if args.command == "tasks":
        payload = executor.tasks_report()
        return _emit(payload, as_json=args.json)
    if args.command == "task-maintain":
        payload = maintainer.run(once=args.once or args.max_cycles is None, max_cycles=args.max_cycles)
        return _emit(payload, as_json=True if args.json or args.once else False)
    if args.command == "hooks":
        payload = executor.hooks_report(tool_name=args.tool, path=args.path)
        return _emit(payload, as_json=args.json)
    if args.command == "compact":
        payload = executor.compact_report(args.input or "")
        return _emit(payload, as_json=args.json)
    if args.command == "study-digest":
        payload = executor.study_digest_report(args.input)
        return _emit(payload, as_json=args.json)
    if args.command == "marketplace-watch":
        envelope = executor.run_marketplace_watch(
            top_limit=args.top_limit,
            sample_data=args.sample_data,
            headless=args.headless,
        )
        if args.notify_telegram and telegram.is_configured:
            dashboard = next((artifact for artifact in envelope.artifacts if artifact.kind == "html"), None)
            if dashboard:
                telegram.send_file(dashboard.path, caption=envelope.final_summary)
        if args.headless or args.json:
            return _emit(build_n8n_payload(envelope), as_json=True)
        return _emit(
            {
                "run_id": envelope.run_id,
                "summary": envelope.final_summary,
                "artifacts": [artifact.path for artifact in envelope.artifacts],
            },
            as_json=False,
        )
    if args.command == "sales-sheet-init":
        payload = executor.sales_sheet_init_report()
        return _emit(payload, as_json=True if args.json else False)
    if args.command == "sales-sheet-refresh":
        payload = executor.sales_sheet_refresh_report(scope=args.scope)
        return _emit(payload, as_json=True if args.json else False)
    if args.command == "sales-sheet-diagnose":
        payload = executor.sales_sheet_diagnose_report()
        return _emit(payload, as_json=True if args.json else False)
    if args.command == "telegram-bot":
        payload = telegram_bot.run_polling(once=args.once, max_cycles=args.max_cycles)
        return _emit(payload, as_json=True if args.json or args.once else False)
    parser.error("Unknown command")
    return 2


def _emit(payload: object, *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if isinstance(payload, dict):
        for key, value in payload.items():
            print(f"{key}: {value}")
        return 0
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
