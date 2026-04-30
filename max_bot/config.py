from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and os.getenv(key) is None:
            os.environ[key] = value.strip().strip('"').strip("'")


_load_dotenv()


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class Settings:
    max_access_token: str
    app_env: str
    max_api_base_url: str
    max_required_chat_id: int
    privacy_policy_url: str
    db_path: str
    poll_timeout_seconds: int
    poll_sleep_seconds: float
    webhook_host: str
    webhook_port: int
    webhook_path: str
    webhook_secret: str | None
    webhook_url: str | None
    log_level: str
    debug_updates: bool
    analytics_spreadsheet_id: str | None
    google_service_account_file: str | None


def load_settings() -> Settings:
    default_env = "local" if os.name == "nt" else "server"
    app_env = (_env("MAX_APP_ENV", default_env) or default_env).lower()
    token = _env("MAX_ACCESS_TOKEN_LOCAL") if app_env in {"local", "dev", "development"} else _env("MAX_ACCESS_TOKEN")
    if not token:
        token = _env("MAX_BOT_API_KEY")
    if not token:
        raise RuntimeError("MAX_ACCESS_TOKEN is required")

    required_chat_id = _env("MAX_REQUIRED_CHAT_ID")
    if required_chat_id is None:
        raise RuntimeError("MAX_REQUIRED_CHAT_ID is required")
    try:
        chat_id = int(required_chat_id)
    except ValueError as exc:
        raise RuntimeError("MAX_REQUIRED_CHAT_ID must be integer") from exc

    return Settings(
        max_access_token=token,
        app_env=app_env,
        max_api_base_url=_env("MAX_API_BASE_URL", "https://platform-api.max.ru") or "https://platform-api.max.ru",
        max_required_chat_id=chat_id,
        privacy_policy_url=_env("PRIVACY_POLICY_URL", "https://adkcosmetics.ru/privacy") or "https://adkcosmetics.ru/privacy",
        db_path=_env("MAX_BOT_DB_PATH", "max_bot/data/bot.db") or "max_bot/data/bot.db",
        poll_timeout_seconds=_env_int("MAX_POLL_TIMEOUT_SECONDS", 25),
        poll_sleep_seconds=float(_env("MAX_POLL_SLEEP_SECONDS", "1.0") or "1.0"),
        webhook_host=_env("MAX_WEBHOOK_HOST", "127.0.0.1") or "127.0.0.1",
        webhook_port=_env_int("MAX_WEBHOOK_PORT", 8085),
        webhook_path=_env("MAX_WEBHOOK_PATH", "/max/webhook") or "/max/webhook",
        webhook_secret=_env("MAX_WEBHOOK_SECRET"),
        webhook_url=_env("MAX_WEBHOOK_URL"),
        log_level=_env("LOG_LEVEL", "INFO") or "INFO",
        debug_updates=(_env("MAX_DEBUG_UPDATES", "0") or "0").lower() in {"1", "true", "yes"},
        analytics_spreadsheet_id=_env("BOT_ANALYTICS_SPREADSHEET_ID"),
        google_service_account_file=_env("GOOGLE_SERVICE_ACCOUNT_FILE"),
    )
