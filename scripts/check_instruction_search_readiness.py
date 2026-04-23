from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


REQUIRED_TABLES = (
    "instruction_index",
    "instruction_sync_state",
)
SUPPORTED_PLATFORMS = ("telegram", "max")


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-check local instruction search index readiness.",
    )
    parser.add_argument("--db-path", required=True, help="Path to the local SQLite index database.")
    parser.add_argument(
        "--platform",
        action="append",
        choices=SUPPORTED_PLATFORMS,
        help="Platform to validate. Repeat to check multiple platforms. Defaults to all supported platforms.",
    )
    parser.add_argument(
        "--min-active-rows",
        type=int,
        default=1,
        help="Minimum number of active indexed rows required per checked platform.",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Only verify the database file and required tables, without requiring indexed rows.",
    )
    return parser.parse_args()


def _fail(message: str) -> int:
    print(f"FAIL: {message}")
    return 1


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(row[0]) for row in rows}


def _active_count(conn: sqlite3.Connection, platform: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM instruction_index
        WHERE source_platform = ? AND status = 'active'
        """,
        (platform,),
    ).fetchone()
    return int(row[0] if row else 0)


def _sample_titles(conn: sqlite3.Connection, platform: str, limit: int = 3) -> list[str]:
    rows = conn.execute(
        """
        SELECT display_title
        FROM instruction_index
        WHERE source_platform = ? AND status = 'active'
        ORDER BY rank_weight DESC, display_title ASC
        LIMIT ?
        """,
        (platform, limit),
    ).fetchall()
    return [str(row[0]) for row in rows if row and row[0]]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = _args()
    db_path = Path(args.db_path)
    platforms = args.platform or list(SUPPORTED_PLATFORMS)

    if args.min_active_rows < 0:
        return _fail("--min-active-rows must be >= 0")
    if not db_path.exists():
        return _fail(f"database does not exist: {db_path}")
    if not db_path.is_file():
        return _fail(f"path is not a file: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        existing_tables = _table_names(conn)
        missing_tables = [table for table in REQUIRED_TABLES if table not in existing_tables]
        if missing_tables:
            return _fail(f"missing required tables: {', '.join(missing_tables)}")

        total_rows = conn.execute("SELECT COUNT(*) FROM instruction_index").fetchone()
        sync_rows = conn.execute("SELECT COUNT(*) FROM instruction_sync_state").fetchone()
        print(f"OK: schema present in {db_path}")
        print(f"instruction_index rows: {int(total_rows[0] if total_rows else 0)}")
        print(f"instruction_sync_state rows: {int(sync_rows[0] if sync_rows else 0)}")

        if args.schema_only:
            print("Schema-only mode enabled; skipping platform row-count checks.")
            return 0

        for platform in platforms:
            count = _active_count(conn, platform)
            if count < args.min_active_rows:
                return _fail(
                    f"platform '{platform}' has {count} active rows; expected at least {args.min_active_rows}"
                )
            samples = _sample_titles(conn, platform)
            sample_text = ", ".join(samples) if samples else "(no sample titles)"
            print(f"{platform}: {count} active rows")
            print(f"{platform} samples: {sample_text}")

        print("Instruction search index is ready for smoke validation.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
