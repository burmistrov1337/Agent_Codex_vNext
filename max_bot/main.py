from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import OrderedDict
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
from time import monotonic

from bot_analytics import BotAnalytics
from instruction_search import InstructionSearchService

from .config import load_settings
from .database import Database
from .handlers import Context, handle_bot_started, handle_callback, handle_message
from .max_api import MaxApiClient, MaxApiError


def _iter_updates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    updates = payload.get("updates") or payload.get("items") or []
    if isinstance(updates, dict):
        return [updates]
    return list(updates)


_DEDUPE_TTL_SECONDS = 45.0
_recent_update_keys: OrderedDict[str, float] = OrderedDict()


def _remember_once(key: str) -> bool:
    now = monotonic()
    stale_keys = [k for k, ts in _recent_update_keys.items() if (now - ts) > _DEDUPE_TTL_SECONDS]
    for stale in stale_keys:
        _recent_update_keys.pop(stale, None)

    if key in _recent_update_keys:
        return False

    _recent_update_keys[key] = now
    return True


def _start_dedupe_key(update: dict[str, Any]) -> str | None:
    update_type = str(update.get("update_type") or update.get("type") or "")

    if update_type == "bot_started":
        user = update.get("user") or {}
        uid = user.get("user_id") or user.get("id")
        return f"start:{uid}" if uid is not None else None

    if update_type not in {"message_created", "message_new", "message"}:
        return None

    message = update.get("message") or {}
    body = message.get("body") or {}
    text = body.get("text")
    if not isinstance(text, str):
        raw = message.get("text")
        text = raw if isinstance(raw, str) else ""
    if text.strip().lower() not in {"/start", "start"}:
        return None

    sender = message.get("sender") or {}
    user = message.get("user") or {}
    uid = (
        sender.get("user_id")
        or sender.get("id")
        or user.get("user_id")
        or user.get("id")
        or message.get("sender_id")
    )
    return f"start:{uid}" if uid is not None else None


def _write_heartbeat(marker: str | None, updates_count: int) -> None:
    runtime_dir = Path(__file__).resolve().parent / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    heartbeat_path = runtime_dir / "heartbeat.json"
    payload = {
        "ts_unix": int(datetime.now(tz=timezone.utc).timestamp()),
        "ts_utc": datetime.now(tz=timezone.utc).isoformat(),
        "marker": marker,
        "updates_count": updates_count,
    }
    heartbeat_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


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
    lock_path = lock_dir / "max_bot.lock"
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
        raise RuntimeError(f"Another max_bot instance is running (pid={existing_pid})")
    if lock_path.exists():
        lock_path.unlink()
    if create_exclusive():
        return lock_path
    raise RuntimeError("Cannot acquire process lock")


async def run_polling() -> None:
    settings = load_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    db = Database(settings.db_path)
    await db.init()
    client = MaxApiClient(settings.max_access_token, settings.max_api_base_url)
    analytics = BotAnalytics(settings.analytics_spreadsheet_id, settings.google_service_account_file)
    instruction_search_service = InstructionSearchService(settings.db_path)
    ctx = Context(
        client=client,
        db=db,
        required_chat_id=settings.max_required_chat_id,
        privacy_policy_url=settings.privacy_policy_url,
        bot_env=settings.app_env,
        analytics=analytics,
        instruction_search_service=instruction_search_service,
    )

    marker: str | None = None
    try:
        while True:
            try:
                payload = await client.get_updates(settings.poll_timeout_seconds, marker)
                marker = payload.get("marker") or marker
                updates = _iter_updates(payload)
                _write_heartbeat(marker, len(updates))
                for update in updates:
                    if settings.debug_updates:
                        logging.info("MAX update raw: %s", json.dumps(update, ensure_ascii=False))

                    dedupe_key = _start_dedupe_key(update)
                    if dedupe_key and not _remember_once(dedupe_key):
                        continue

                    update_type = update.get("update_type") or update.get("type") or ""
                    if update_type == "message_callback":
                        await handle_callback(ctx, update)
                    elif update_type in {"message_created", "message_new", "message"}:
                        await handle_message(ctx, update)
                    elif update_type == "bot_started":
                        await handle_bot_started(ctx, update)
            except MaxApiError as exc:
                logging.warning("MAX API error: %s", exc)
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
