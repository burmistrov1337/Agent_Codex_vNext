from __future__ import annotations

import argparse

from agent_codex.apps.cli.main import main as codex_main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent_system.cli")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--wb-tnved-ui-catalog", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.wb_tnved_ui_catalog:
        parser.error("Specify --wb-tnved-ui-catalog")
        return 2
    forwarded = ["wb-tnved-ui-catalog", "--project-root", args.project_root]
    if args.json:
        forwarded.append("--json")
    return codex_main(forwarded)


if __name__ == "__main__":
    raise SystemExit(main())

