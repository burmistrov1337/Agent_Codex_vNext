from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts._env import load_repo_dotenv
from instruction_search import rebuild_platform_index
from instruction_search.sheets import SheetsWorkbook


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=["telegram", "max"], required=True)
    parser.add_argument("--db-path")
    return parser.parse_args()


def _resolve_db_path(platform: str, db_path: str | None) -> str:
    resolved = (db_path or "").strip()
    if resolved:
        return resolved
    if platform == "max":
        from max_bot.config import load_settings

        return load_settings().db_path
    raise RuntimeError("--db-path is required for platform=telegram")


async def _run() -> None:
    args = _args()
    load_repo_dotenv()
    spreadsheet_id = (os.getenv("BOT_ANALYTICS_SPREADSHEET_ID") or "").strip()
    service_account_file = (os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE") or "").strip()
    if not spreadsheet_id or not service_account_file:
        raise RuntimeError("BOT_ANALYTICS_SPREADSHEET_ID and GOOGLE_SERVICE_ACCOUNT_FILE are required")
    workbook = SheetsWorkbook(spreadsheet_id, service_account_file)
    db_path = _resolve_db_path(args.platform, args.db_path)
    count = await rebuild_platform_index(workbook, platform=args.platform, sqlite_db_path=db_path)
    db_count = 0
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM instruction_index WHERE source_platform=? AND status='active'",
                (args.platform,),
            ).fetchone()
            db_count = int(row[0] if row else 0)
        finally:
            conn.close()
    except Exception:
        db_count = count
    print(f"Indexed {max(count, db_count)} instructions for {args.platform} into {db_path}.")


if __name__ == "__main__":
    asyncio.run(_run())
