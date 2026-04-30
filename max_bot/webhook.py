from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiohttp import web

from .config import load_settings
from .main import build_context, process_update
from .max_api import MaxApiClient


def _write_webhook_heartbeat(update_type: str | None) -> None:
    runtime_dir = Path(__file__).resolve().parent / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts_unix": int(datetime.now(tz=timezone.utc).timestamp()),
        "ts_utc": datetime.now(tz=timezone.utc).isoformat(),
        "mode": "webhook",
        "update_type": update_type,
    }
    (runtime_dir / "heartbeat.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


async def _handle_update(app: web.Application, update: dict[str, Any]) -> None:
    settings = app["settings"]
    ctx = app["ctx"]
    try:
        await process_update(ctx, update, debug_updates=settings.debug_updates)
    except Exception:
        logging.exception("Unhandled error while processing MAX webhook update")


async def webhook_handler(request: web.Request) -> web.Response:
    settings = request.app["settings"]
    expected_secret = settings.webhook_secret
    if expected_secret:
        actual_secret = request.headers.get("X-Max-Bot-Api-Secret", "")
        if actual_secret != expected_secret:
            return web.json_response({"ok": False, "error": "invalid secret"}, status=403)

    try:
        update = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)

    if not isinstance(update, dict):
        return web.json_response({"ok": False, "error": "invalid update"}, status=400)

    update_type = update.get("update_type") or update.get("type")
    _write_webhook_heartbeat(str(update_type) if update_type else None)
    task = asyncio.create_task(_handle_update(request.app, update))
    request.app["tasks"].add(task)
    task.add_done_callback(request.app["tasks"].discard)
    return web.json_response({"ok": True})


async def health_handler(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "max_bot_webhook"})


async def register_subscription() -> None:
    settings = load_settings()
    if not settings.webhook_url:
        raise RuntimeError("MAX_WEBHOOK_URL is required to register webhook subscription")
    client = MaxApiClient(settings.max_access_token, settings.max_api_base_url)
    try:
        result = await client.create_subscription(
            settings.webhook_url,
            update_types=["message_created", "message_callback", "bot_started"],
            secret=settings.webhook_secret,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        await client.close()


async def create_app() -> web.Application:
    settings = load_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    app = web.Application()
    app["settings"] = settings
    app["ctx"] = await build_context()
    app["tasks"] = set()
    webhook_path = settings.webhook_path if settings.webhook_path.startswith("/") else f"/{settings.webhook_path}"
    app.router.add_post(webhook_path, webhook_handler)
    app.router.add_get("/health", health_handler)

    async def cleanup(app: web.Application) -> None:
        tasks = set(app["tasks"])
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await app["ctx"].client.close()

    app.on_cleanup.append(cleanup)
    return app


def main() -> None:
    settings = load_settings()
    app = create_app()
    web.run_app(app, host=settings.webhook_host, port=settings.webhook_port)


if __name__ == "__main__":
    main()
