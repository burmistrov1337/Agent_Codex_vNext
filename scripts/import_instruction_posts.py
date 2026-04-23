from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts._env import load_repo_dotenv
from instruction_search.importers import load_export_rows
from instruction_search.sheets import SheetsWorkbook
from instruction_search.sync import POSTS_MAX_SHEET, POSTS_TELEGRAM_SHEET, POST_HEADERS, bootstrap_instruction_workbook


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=["telegram", "max"], required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--channel-name")
    parser.add_argument("--channel-id")
    parser.add_argument("--replace-sheet", action="store_true")
    return parser.parse_args()


def _resolve_telegram_export_metadata(
    input_path: str,
    channel_name: str | None,
    channel_id: str | None,
) -> tuple[str | None, str | None]:
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return channel_name, channel_id

    if not isinstance(payload.get("messages"), list):
        resolved_channel_name = (channel_name or str(payload.get("channel_name") or payload.get("name") or "")).strip() or None
        resolved_channel_id = (channel_id or str(payload.get("channel_id") or payload.get("id") or "")).strip() or None
        return resolved_channel_name, resolved_channel_id

    resolved_channel_name = (channel_name or str(payload.get("name") or "")).strip() or None
    root_id = payload.get("id")
    resolved_channel_id = (channel_id or (str(root_id).strip() if root_id is not None else "")).strip() or None
    return resolved_channel_name, resolved_channel_id


def _resolve_generic_export_metadata(
    input_path: str,
    channel_name: str | None,
    channel_id: str | None,
) -> tuple[str | None, str | None]:
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return channel_name, channel_id
    resolved_channel_name = (channel_name or str(payload.get("channel_name") or payload.get("name") or "")).strip() or None
    resolved_channel_id = (channel_id or str(payload.get("channel_id") or payload.get("id") or "")).strip() or None
    return resolved_channel_name, resolved_channel_id


def _merge_post_rows(existing: list[list[str]], incoming: list[list[Any]]) -> list[list[str]]:
    header = POST_HEADERS
    key_indexes = {
        "source_platform": header.index("source_platform"),
        "source_channel_id": header.index("source_channel_id"),
        "source_post_id": header.index("source_post_id"),
        "post_url": header.index("post_url"),
    }

    merged: dict[tuple[str, str, str], list[str]] = {}
    ordered_keys: list[tuple[str, str, str]] = []

    def _normalize_row(row: list[Any]) -> list[str]:
        values = [str(cell) for cell in row[: len(header)]]
        if len(values) < len(header):
            values.extend([""] * (len(header) - len(values)))
        return values

    def _key(values: list[str]) -> tuple[str, str, str]:
        # Prefer source_post_id: for MAX browser exports post_url can be the same
        # channel URL for many rows and would collapse distinct posts.
        stable_ref = values[key_indexes["source_post_id"]].strip() or values[key_indexes["post_url"]].strip()
        return (
            values[key_indexes["source_platform"]].strip(),
            values[key_indexes["source_channel_id"]].strip(),
            stable_ref,
        )

    for row in existing[1:]:
        values = _normalize_row(row)
        row_key = _key(values)
        if not row_key[-1]:
            continue
        merged[row_key] = values
        if row_key not in ordered_keys:
            ordered_keys.append(row_key)

    for row in incoming:
        values = _normalize_row(row)
        row_key = _key(values)
        if not row_key[-1]:
            continue
        if row_key not in merged:
            ordered_keys.append(row_key)
        merged[row_key] = values

    return [header] + [merged[row_key] for row_key in ordered_keys if row_key in merged]


def main() -> None:
    args = _args()
    if args.replace_sheet and args.platform != "max":
        raise RuntimeError("--replace-sheet is allowed only for platform=max")
    load_repo_dotenv()
    spreadsheet_id = (os.getenv("BOT_ANALYTICS_SPREADSHEET_ID") or "").strip()
    service_account_file = (os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE") or "").strip()
    if not spreadsheet_id or not service_account_file:
        raise RuntimeError("BOT_ANALYTICS_SPREADSHEET_ID and GOOGLE_SERVICE_ACCOUNT_FILE are required")
    workbook = SheetsWorkbook(spreadsheet_id, service_account_file)
    bootstrap_instruction_workbook(workbook)

    channel_name = (args.channel_name or "").strip() or None
    channel_id = (args.channel_id or "").strip() or None
    if args.platform == "telegram":
        channel_name, channel_id = _resolve_telegram_export_metadata(args.input, channel_name, channel_id)
    else:
        channel_name, channel_id = _resolve_generic_export_metadata(args.input, channel_name, channel_id)
    if not channel_name or not channel_id:
        raise RuntimeError("--channel-name and --channel-id are required when the export file does not provide them")
    rows = load_export_rows(args.input, args.platform, channel_name, channel_id)

    sheet_name = POSTS_TELEGRAM_SHEET if args.platform == "telegram" else POSTS_MAX_SHEET
    if args.replace_sheet:
        if args.platform != "max":
            raise RuntimeError("--replace-sheet is supported only for platform=max to avoid accidental replacement of other sheets")
        workbook.rewrite_sheet(sheet_name, POST_HEADERS, rows)
    else:
        existing = workbook.read_rows(sheet_name)
        merged = _merge_post_rows(existing, rows)
        workbook.rewrite_sheet(sheet_name, POST_HEADERS, merged[1:])
    print(
        f"Imported {len(rows)} rows into {sheet_name} "
        f"(replace_sheet={'yes' if args.replace_sheet else 'no'}, "
        f"channel_name={channel_name or 'n/a'}, channel_id={channel_id or 'n/a'})."
    )


if __name__ == "__main__":
    main()
