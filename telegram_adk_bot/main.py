from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from bot_analytics import BotAnalytics
from instruction_search import InstructionSearchService

from .config import load_settings
from .database import Database
from .handlers import Context, handle_callback, handle_message
from .telegram_api import TelegramApiClient, TelegramApiError


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _acquire_single_lock() -> Path:
    lock_dir = Path(__file__).resolve().parent / "runtime"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "telegram_adk_bot.lock"
    current_pid = os.getpid()

    def create_exclusive() -> bool:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(current_pid).encode("utf-8"))
            finally:
                os.close(fd)
            return True
        except FileExistsError:
            return False

    if create_exclusive():
        return lock_path

    raw = lock_path.read_text(encoding="utf-8", errors="replace").strip() if lock_path.exists() else ""
    try:
        existing_pid = int(raw)
    except ValueError:
        existing_pid = 0
    if existing_pid and existing_pid != current_pid and _pid_alive(existing_pid):
        raise RuntimeError(f"Another telegram_adk_bot instance is running (pid={existing_pid})")
    if lock_path.exists():
        lock_path.unlink()
    if create_exclusive():
        return lock_path
    raise RuntimeError("Cannot acquire process lock")


def _write_heartbeat(last_update_id: int | None, updates_count: int) -> None:
    runtime_dir = Path(__file__).resolve().parent / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts_unix": int(datetime.now(tz=timezone.utc).timestamp()),
        "ts_utc": datetime.now(tz=timezone.utc).isoformat(),
        "last_update_id": last_update_id,
        "updates_count": updates_count,
    }
    (runtime_dir / "heartbeat.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


async def run_polling() -> None:
    settings = load_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    db = Database(settings.db_path)
    await db.init()
    client = TelegramApiClient(settings.telegram_token)
    analytics = BotAnalytics(settings.analytics_spreadsheet_id, settings.google_service_account_file)
    instruction_search_service = InstructionSearchService(settings.db_path)
    ctx = Context(
        client=client,
        db=db,
        required_chat=settings.required_chat,
        privacy_policy_url=settings.privacy_policy_url,
        bot_env=settings.app_env,
        analytics=analytics,
        instruction_search_service=instruction_search_service,
    )

    offset: int | None = None
    try:
        while True:
            try:
                updates = await client.get_updates(offset, settings.poll_timeout_seconds)
                if updates:
                    offset = int(updates[-1]["update_id"]) + 1
                _write_heartbeat(offset, len(updates))
                for update in updates:
                    if settings.debug_updates:
                        logging.info("TG update raw: %s", json.dumps(update, ensure_ascii=False))
                    if "message" in update:
                        await handle_message(ctx, update["message"])
                    elif "callback_query" in update:
                        await handle_callback(ctx, update["callback_query"])
            except TelegramApiError as exc:
                logging.warning("Telegram API error: %s", exc)
                await asyncio.sleep(2)
            except Exception as exc:
                if settings.debug_updates:
                    logging.exception("Unhandled error in polling loop")
                else:
                    logging.warning("Unhandled error in polling loop: %s", exc)
                await asyncio.sleep(2)
            await asyncio.sleep(settings.poll_sleep_seconds)
    finally:
        await client.close()


def main() -> None:
    lock_path = _acquire_single_lock()
    try:
        asyncio.run(run_polling())
    finally:
        try:
            if lock_path.exists():
                lock_path.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    main()
