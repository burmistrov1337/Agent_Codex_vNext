from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    risk: str = "low"
    protected_patterns: list[str] = field(default_factory=list)


def default_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(name="read_file", description="Read local files", risk="low"),
        ToolSpec(name="write_file", description="Write local files", risk="medium"),
        ToolSpec(name="shell", description="Run local shell command", risk="medium"),
        ToolSpec(name="telegram_send", description="Send Telegram message or document", risk="low"),
        ToolSpec(name="wb_api", description="Call Wildberries APIs", risk="low"),
    ]
