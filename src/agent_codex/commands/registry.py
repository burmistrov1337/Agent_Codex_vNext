from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    description: str


COMMANDS = [
    CommandSpec("doctor", "Check config, layout, and adapter wiring."),
    CommandSpec("metrics", "Collect runtime metrics for memory, tasks, artifacts, and backend setup."),
    CommandSpec("memory", "Show memory index and optionally run consolidation."),
    CommandSpec("review", "Check text against synthesis rules."),
    CommandSpec("tasks", "Show current runtime task files."),
    CommandSpec("task-maintain", "Run recovery/maintenance cycle for TaskBus."),
    CommandSpec("hooks", "Inspect how policy evaluates an action or path."),
    CommandSpec("compact", "Compact long text into a short management summary."),
    CommandSpec("marketplace-watch", "Build marketplace watch and headless envelope."),
    CommandSpec("sales-sheet-init", "Initialize the Google Sheets sales workbook skeleton."),
    CommandSpec("sales-sheet-refresh", "Refresh sales raw data, calculations, and actions."),
    CommandSpec("sales-sheet-diagnose", "Check sales workbook config, access, and freshness."),
    CommandSpec("study-digest", "Prepare a short digest of a study text."),
    CommandSpec("telegram-bot", "Start Telegram ingress with long polling for async tasks."),
]
