from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts._env import load_repo_dotenv
from instruction_search import bootstrap_instruction_workbook
from instruction_search.sheets import SheetsWorkbook


def main() -> None:
    load_repo_dotenv()
    spreadsheet_id = (os.getenv("BOT_ANALYTICS_SPREADSHEET_ID") or "").strip()
    service_account_file = (os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE") or "").strip()
    if not spreadsheet_id or not service_account_file:
        raise RuntimeError("BOT_ANALYTICS_SPREADSHEET_ID and GOOGLE_SERVICE_ACCOUNT_FILE are required")
    workbook = SheetsWorkbook(spreadsheet_id, service_account_file)
    bootstrap_instruction_workbook(workbook)
    print("Instruction search sheets are ready.")


if __name__ == "__main__":
    main()
