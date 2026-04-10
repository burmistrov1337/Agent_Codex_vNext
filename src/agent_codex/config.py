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
    openai_api_key: str | None
    openai_model: str
    anthropic_api_key: str | None
    anthropic_model: str
    ollama_base_url: str
    ollama_model: str
    marketplace_artifact_root: Path
    sales_artifact_root: Path
    wb_api_timeout_seconds: int
    google_sheets_spreadsheet_id: str | None
    google_service_account_file: Path | None
    google_service_account_json: str | None
    sales_sheet_refresh_cron: str
    sales_sheet_webhook_secret: str | None
    advantshop_api_url: str | None
    advantshop_api: str | None
    advantshop_api_auth: str | None

    def validate(self) -> list[str]:
        issues: list[str] = []
        supported_backends = {"deterministic", "null", "groq", "openai", "anthropic", "ollama"}

        for field_name, backend_name in (
            ("primary_reasoning_backend", self.primary_reasoning_backend),
            ("background_backend", self.background_backend),
            ("cheap_backend", self.cheap_backend),
        ):
            if backend_name not in supported_backends:
                issues.append(
                    f"{field_name} uses unsupported backend '{backend_name}'. "
                    f"Supported values: {', '.join(sorted(supported_backends))}."
                )
            if backend_name == "groq" and not self.groq_api_key:
                issues.append(f"{field_name} is set to 'groq', but GROQ_API_KEY is not configured.")
            if backend_name == "openai" and not self.openai_api_key:
                issues.append(f"{field_name} is set to 'openai', but OPENAI_API_KEY is not configured.")
            if backend_name == "anthropic" and not self.anthropic_api_key:
                issues.append(f"{field_name} is set to 'anthropic', but ANTHROPIC_API_KEY is not configured.")
            if backend_name == "ollama" and not self.ollama_base_url.strip():
                issues.append(f"{field_name} is set to 'ollama', but OLLAMA_BASE_URL is empty.")

        if self.telegram_bot_token and not self.telegram_allowed_chat_id:
            issues.append("TELEGRAM_ALLOWED_CHAT_ID or TELEGRAM_CHAT_ID must be configured when TELEGRAM_BOT_TOKEN is set.")

        has_google_credentials = bool(self.google_service_account_file or self.google_service_account_json)
        if self.google_sheets_spreadsheet_id and not has_google_credentials:
            issues.append(
                "Google Sheets is configured, but GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON is missing."
            )
        if has_google_credentials and not self.google_sheets_spreadsheet_id:
            issues.append(
                "Google service account credentials are configured, but GOOGLE_SHEETS_SPREADSHEET_ID is missing."
            )
        if self.google_service_account_file and not self.google_service_account_file.exists():
            issues.append(
                f"GOOGLE_SERVICE_ACCOUNT_FILE points to a missing file: {self.google_service_account_file}."
            )

        has_advantshop_credentials = bool(self.advantshop_api or self.advantshop_api_auth)
        if self.advantshop_api_url and not has_advantshop_credentials:
            issues.append("ADVANTSHOP_API_URL is configured, but ADVANTSHOP_API or ADVANTSHOP_API_AUTH is missing.")
        if has_advantshop_credentials and not self.advantshop_api_url:
            issues.append("ADVANTSHOP_API or ADVANTSHOP_API_AUTH is configured, but ADVANTSHOP_API_URL is missing.")

        if self.wb_api_timeout_seconds <= 0:
            issues.append("WB_API_TIMEOUT_SECONDS must be greater than zero.")
        if self.openai_model.strip() == "":
            issues.append("OPENAI_MODEL must not be empty.")
        if self.anthropic_model.strip() == "":
            issues.append("ANTHROPIC_MODEL must not be empty.")
        if self.ollama_model.strip() == "":
            issues.append("OLLAMA_MODEL must not be empty.")

        return issues


def load_settings(project_root: str | Path = ".") -> Settings:
    root = Path(project_root).resolve()
    env = _load_dotenv(root / ".env")
    runtime_root = root / env.get("RUNTIME_ROOT", ".agent_codex")
    artifact_root = root / env.get("MARKETPLACE_ARTIFACT_ROOT", ".agent_codex/artifacts/marketplace")
    sales_artifact_root = root / env.get("SALES_ARTIFACT_ROOT", ".agent_codex/artifacts/sales")
    telegram_inbox_root = root / env.get("TELEGRAM_INBOX_ROOT", ".agent_codex/telegram/inbox")
    telegram_state_root = root / env.get("TELEGRAM_STATE_ROOT", ".agent_codex/telegram/state")
    google_service_account_file_value = (
        env.get("GOOGLE_SERVICE_ACCOUNT_FILE") or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    )
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
        wb_api_timeout_seconds=int(
            env.get("WB_API_TIMEOUT_SECONDS")
            or os.getenv("WB_API_TIMEOUT_SECONDS")
            or "30"
        ),
        primary_reasoning_backend=env.get("PRIMARY_REASONING_BACKEND") or os.getenv("PRIMARY_REASONING_BACKEND") or "deterministic",
        background_backend=env.get("BACKGROUND_BACKEND") or os.getenv("BACKGROUND_BACKEND") or "deterministic",
        cheap_backend=env.get("CHEAP_BACKEND") or os.getenv("CHEAP_BACKEND") or "deterministic",
        groq_api_key=env.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY"),
        groq_model=env.get("GROQ_MODEL") or os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile",
        openai_api_key=env.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"),
        openai_model=env.get("OPENAI_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-5.4-mini",
        anthropic_api_key=env.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY"),
        anthropic_model=env.get("ANTHROPIC_MODEL") or os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-5",
        ollama_base_url=env.get("OLLAMA_BASE_URL") or os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434",
        ollama_model=env.get("OLLAMA_MODEL") or os.getenv("OLLAMA_MODEL") or "llama3.1:8b",
        marketplace_artifact_root=artifact_root.resolve(),
        sales_artifact_root=sales_artifact_root.resolve(),
        google_sheets_spreadsheet_id=(
            env.get("GOOGLE_SHEETS_SPREADSHEET_ID") or os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
        ),
        google_service_account_file=Path(google_service_account_file_value).resolve() if google_service_account_file_value else None,
        google_service_account_json=(
            env.get("GOOGLE_SERVICE_ACCOUNT_JSON") or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        ),
        sales_sheet_refresh_cron=(
            env.get("SALES_SHEET_REFRESH_CRON")
            or os.getenv("SALES_SHEET_REFRESH_CRON")
            or "0 8 * * *"
        ),
        sales_sheet_webhook_secret=(
            env.get("SALES_SHEET_WEBHOOK_SECRET") or os.getenv("SALES_SHEET_WEBHOOK_SECRET")
        ),
        advantshop_api_url=(
            env.get("ADVANTSHOP_API_URL")
            or env.get("advantshop_api_url")
            or os.getenv("ADVANTSHOP_API_URL")
        ),
        advantshop_api=(
            env.get("ADVANTSHOP_API")
            or env.get("advantshop_api")
            or os.getenv("ADVANTSHOP_API")
        ),
        advantshop_api_auth=(
            env.get("ADVANTSHOP_API_AUTH")
            or env.get("advantshop_api_auth")
            or os.getenv("ADVANTSHOP_API_AUTH")
        ),
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
        settings.sales_artifact_root,
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
