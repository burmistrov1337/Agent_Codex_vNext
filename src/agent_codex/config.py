from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Settings:
    project_root: Path
    runtime_root: Path
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    telegram_allowed_chat_id: str | None
    telegram_poll_timeout_seconds: int
    telegram_inbox_root: Path
    telegram_state_root: Path
    wb_api_token: str | None
    primary_reasoning_backend: str
    background_backend: str
    cheap_backend: str
    groq_api_key: str | None
    groq_model: str
    marketplace_artifact_root: Path


def load_settings(project_root: str | Path = ".") -> Settings:
    root = Path(project_root).resolve()
    env = _load_dotenv(root / ".env")
    runtime_root = root / env.get("RUNTIME_ROOT", ".agent_codex")
    artifact_root = root / env.get("MARKETPLACE_ARTIFACT_ROOT", ".agent_codex/artifacts/marketplace")
    telegram_inbox_root = root / env.get("TELEGRAM_INBOX_ROOT", ".agent_codex/telegram/inbox")
    telegram_state_root = root / env.get("TELEGRAM_STATE_ROOT", ".agent_codex/telegram/state")
    return Settings(
        project_root=root,
        runtime_root=runtime_root,
        telegram_bot_token=env.get("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=env.get("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID"),
        telegram_allowed_chat_id=(
            env.get("TELEGRAM_ALLOWED_CHAT_ID")
            or os.getenv("TELEGRAM_ALLOWED_CHAT_ID")
            or env.get("TELEGRAM_CHAT_ID")
            or os.getenv("TELEGRAM_CHAT_ID")
        ),
        telegram_poll_timeout_seconds=int(env.get("TELEGRAM_POLL_TIMEOUT_SECONDS", "20")),
        telegram_inbox_root=telegram_inbox_root.resolve(),
        telegram_state_root=telegram_state_root.resolve(),
        wb_api_token=env.get("WB_API_TOKEN") or env.get("WILDBERRIES_API_TOKEN") or os.getenv("WB_API_TOKEN"),
        primary_reasoning_backend=env.get("PRIMARY_REASONING_BACKEND", "deterministic"),
        background_backend=env.get("BACKGROUND_BACKEND", "deterministic"),
        cheap_backend=env.get("CHEAP_BACKEND", "deterministic"),
        groq_api_key=env.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY"),
        groq_model=env.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        marketplace_artifact_root=artifact_root.resolve(),
    )


def ensure_runtime_layout(settings: Settings) -> None:
    dirs = [
        settings.runtime_root / "memory" / "topics",
        settings.runtime_root / "memory" / "logs",
        settings.runtime_root / "sessions",
        settings.runtime_root / "scratchpad",
        settings.runtime_root / "tasks",
        settings.runtime_root / "audit",
        settings.runtime_root / "artifacts",
        settings.runtime_root / "telegram" / "sessions",
        settings.marketplace_artifact_root,
        settings.telegram_inbox_root,
        settings.telegram_state_root,
    ]
    for path in dirs:
        path.mkdir(parents=True, exist_ok=True)
    memory_index = settings.runtime_root / "memory" / "MEMORY.md"
    if not memory_index.exists():
        memory_index.write_text("# MEMORY\n\n", encoding="utf-8")


def _load_dotenv(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data
