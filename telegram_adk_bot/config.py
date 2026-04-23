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
    telegram_token: str
    app_env: str
    required_chat: str
    privacy_policy_url: str
    db_path: str
    poll_timeout_seconds: int
    poll_sleep_seconds: float
    log_level: str
    debug_updates: bool
    analytics_spreadsheet_id: str | None
    google_service_account_file: str | None


def load_settings() -> Settings:
    app_env = (_env("TELEGRAM_ADK_APP_ENV", "server") or "server").lower()
    token = _env("TELEGRAM_ADK_TEST_BOT_TOKEN") if app_env in {"local", "dev", "development"} else _env("TELEGRAM_ADK_BOT_TOKEN")
    if not token:
        raise RuntimeError("Telegram token is required: TELEGRAM_ADK_BOT_TOKEN (server) or TELEGRAM_ADK_TEST_BOT_TOKEN (local)")

    required_chat = _env("TELEGRAM_ADK_REQUIRED_CHAT", "@ustore_active")
    if not required_chat:
        raise RuntimeError("TELEGRAM_ADK_REQUIRED_CHAT is required")

    return Settings(
        telegram_token=token,
        app_env=app_env,
        required_chat=required_chat,
        privacy_policy_url=_env("PRIVACY_POLICY_URL", "https://adkcosmetics.ru/privacy") or "https://adkcosmetics.ru/privacy",
        db_path=_env("TELEGRAM_ADK_DB_PATH", "telegram_adk_bot/data/bot.db") or "telegram_adk_bot/data/bot.db",
        poll_timeout_seconds=_env_int("TELEGRAM_ADK_POLL_TIMEOUT_SECONDS", 25),
        poll_sleep_seconds=float(_env("TELEGRAM_ADK_POLL_SLEEP_SECONDS", "0.8") or "0.8"),
        log_level=_env("LOG_LEVEL", "INFO") or "INFO",
        debug_updates=(_env("TELEGRAM_ADK_DEBUG_UPDATES", "0") or "0").lower() in {"1", "true", "yes"},
        analytics_spreadsheet_id=_env("BOT_ANALYTICS_SPREADSHEET_ID"),
        google_service_account_file=_env("GOOGLE_SERVICE_ACCOUNT_FILE"),
    )
