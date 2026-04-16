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
    wb_api_timeout_seconds: int

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

    google_sheets_spreadsheet_id: str | None
    google_service_account_file: str | None
    google_service_account_json: str | None
    sales_sheet_refresh_cron: str
    sales_sheet_webhook_secret: str | None

    advantshop_api_url: str | None
    advantshop_api: str | None
    advantshop_api_auth: str | None

    wb_ui_browser_user_data_dir: Path
    wb_ui_browser_profile_directory: str
    wb_ui_browser_channel: str
    wb_ui_browser_executable_path: str | None
    wb_ui_browser_cdp_url: str | None
    wb_ui_seller_url: str
    wb_ui_card_url_template: str

    def validate(self) -> list[str]:
        issues: list[str] = []
        if self.runtime_root == self.project_root:
            issues.append("runtime_root should not be equal to project_root")
        if self.telegram_poll_timeout_seconds <= 0:
            issues.append("telegram_poll_timeout_seconds must be > 0")
        if self.wb_api_timeout_seconds <= 0:
            issues.append("wb_api_timeout_seconds must be > 0")
        if not self.sales_sheet_refresh_cron.strip():
            issues.append("sales_sheet_refresh_cron is empty")
        return issues


def load_settings(project_root: str | Path = ".") -> Settings:
    root = Path(project_root).resolve()
    env = _load_dotenv(root / ".env")

    runtime_root = (root / env.get("RUNTIME_ROOT", ".agent_codex")).resolve()
    marketplace_artifact_root = (root / env.get("MARKETPLACE_ARTIFACT_ROOT", ".agent_codex/artifacts/marketplace")).resolve()
    sales_artifact_root = (root / env.get("SALES_ARTIFACT_ROOT", ".agent_codex/artifacts/sales")).resolve()
    telegram_inbox_root = (root / env.get("TELEGRAM_INBOX_ROOT", ".agent_codex/telegram/inbox")).resolve()
    telegram_state_root = (root / env.get("TELEGRAM_STATE_ROOT", ".agent_codex/telegram/state")).resolve()

    local_app_data = Path(os.getenv("LOCALAPPDATA") or str(root / ".browser_profile"))
    default_user_data_dir = local_app_data / "Google" / "Chrome" / "User Data"

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
        telegram_poll_timeout_seconds=int(env.get("TELEGRAM_POLL_TIMEOUT_SECONDS") or os.getenv("TELEGRAM_POLL_TIMEOUT_SECONDS") or "20"),
        telegram_inbox_root=telegram_inbox_root,
        telegram_state_root=telegram_state_root,
        wb_api_token=env.get("WB_API_TOKEN") or env.get("WILDBERRIES_API_TOKEN") or os.getenv("WB_API_TOKEN"),
        wb_api_timeout_seconds=int(env.get("WB_API_TIMEOUT_SECONDS") or os.getenv("WB_API_TIMEOUT_SECONDS") or "30"),
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
        marketplace_artifact_root=marketplace_artifact_root,
        sales_artifact_root=sales_artifact_root,
        google_sheets_spreadsheet_id=env.get("GOOGLE_SHEETS_SPREADSHEET_ID") or os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID"),
        google_service_account_file=env.get("GOOGLE_SERVICE_ACCOUNT_FILE") or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"),
        google_service_account_json=env.get("GOOGLE_SERVICE_ACCOUNT_JSON") or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"),
        sales_sheet_refresh_cron=env.get("SALES_SHEET_REFRESH_CRON") or os.getenv("SALES_SHEET_REFRESH_CRON") or "0 8 * * *",
        sales_sheet_webhook_secret=env.get("SALES_SHEET_WEBHOOK_SECRET") or os.getenv("SALES_SHEET_WEBHOOK_SECRET"),
        advantshop_api_url=env.get("ADVANTSHOP_API_URL") or os.getenv("ADVANTSHOP_API_URL"),
        advantshop_api=env.get("ADVANTSHOP_API") or env.get("advantshop_api") or os.getenv("ADVANTSHOP_API") or os.getenv("advantshop_api"),
        advantshop_api_auth=env.get("ADVANTSHOP_API_AUTH") or env.get("advantshop_api_auth") or os.getenv("ADVANTSHOP_API_AUTH") or os.getenv("advantshop_api_auth"),
        wb_ui_browser_user_data_dir=(root / env["WB_UI_BROWSER_USER_DATA_DIR"]).resolve()
        if env.get("WB_UI_BROWSER_USER_DATA_DIR")
        else default_user_data_dir.resolve(),
        wb_ui_browser_profile_directory=env.get("WB_UI_BROWSER_PROFILE_DIRECTORY", "Default"),
        wb_ui_browser_channel=env.get("WB_UI_BROWSER_CHANNEL", "chrome"),
        wb_ui_browser_executable_path=env.get("WB_UI_BROWSER_EXECUTABLE_PATH") or None,
        wb_ui_browser_cdp_url=env.get("WB_UI_BROWSER_CDP_URL") or None,
        wb_ui_seller_url=env.get("WB_UI_SELLER_URL", "https://seller.wildberries.ru"),
        wb_ui_card_url_template=env.get(
            "WB_UI_CARD_URL_TEMPLATE",
            "https://seller.wildberries.ru/content-management/cards/card?nmID={nm_id}",
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
