from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from pypdf import PdfReader


FIELD_PATTERNS = {
    "plan": r"Тарифный план:\s*(.+)",
    "opened_at": r"Дата открытия:\s*(.+)",
    "domain": r"Доменное имя:\s*(.+)",
    "host": r"IP-адрес сервера:\s*(.+)",
    "user": r"Пользователь:\s*(.+)",
    "password": r"Пароль:\s*(.+)",
}


def resolve_pdf_path(pdf_path: Path | None) -> Path:
    if pdf_path and pdf_path.exists():
        return pdf_path

    downloads = Path.home() / "Downloads"
    candidates = sorted(downloads.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    for candidate in candidates:
        if "Активация" in candidate.name or "Виртуального" in candidate.name:
            return candidate

    if candidates:
        return candidates[0]

    raise FileNotFoundError("No PDF candidates were found in Downloads.")


def extract_text(pdf_path: Path) -> str:
    reader = PdfReader(pdf_path.open("rb"))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def extract_fields(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for key, pattern in FIELD_PATTERNS.items():
        match = re.search(pattern, text)
        if match:
            data[key] = match.group(1).strip()
    return data


def redact_preview(text: str) -> str:
    return re.sub(r"(Пароль:\s*)(.+)", r"\1[REDACTED]", text)


def write_env(env_path: Path, fields: dict[str, str]) -> None:
    env_lines = [
        "# Extracted from VPS activation PDF. Adjust OPENCLAW_* values if your deployment differs.",
        f"HOST={fields.get('host', '')}",
        "PORT=22",
        f"USER={fields.get('user', 'root')}",
        f"DOMAIN={fields.get('domain', '')}",
        "KEY_PATH=%USERPROFILE%\\.ssh\\agent_codex_server",
        "LOCAL_PORT=38080",
        "OPENCLAW_REMOTE_PORT=3000",
        "OPENCLAW_SCHEME=http",
        "OPENCLAW_PATH=/",
        "STRICT_HOST_KEY_CHECKING=accept-new",
    ]
    env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract VPS credentials from an activation PDF.")
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--env-out", type=Path)
    args = parser.parse_args()

    pdf_path = resolve_pdf_path(args.pdf)
    text = extract_text(pdf_path)
    fields = extract_fields(text)
    safe_fields = dict(fields)
    if "password" in safe_fields:
        safe_fields["password"] = "[REDACTED]"

    payload = {
        "pdf_path": str(pdf_path),
        "extracted": safe_fields,
        "password_present": "password" in fields,
        "missing": [key for key in FIELD_PATTERNS if key not in fields],
        "preview": redact_preview(text[:1500]),
    }

    if args.json_out:
        args.json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.env_out:
        write_env(args.env_out, fields)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
