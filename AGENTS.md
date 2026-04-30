# Workspace Rules

## New Projects (Global Rule)

- For every new project, create a dedicated top-level folder named after the project.
- Inside each project folder, create a project log Markdown file (for example: `PROJECT_LOG.md`) and keep it updated during work.
- The project log must contain: goal, scope, key decisions, completed steps, pending tasks, and important links/files.
- Do not scatter project artifacts across the repository root.

## Project Isolation

- For the `stuurman` project, store all working files only inside `stuurman/` and its subfolders.
- Do not create temporary, draft, export, or analysis files in the repository root.
- If a file is created in the wrong place, move it into `stuurman/` immediately.

## Folder Discipline

- Every new task must use a dedicated subfolder inside `stuurman/` when needed (for example: `stuurman/legal/`, `stuurman/research/`, `stuurman/exports/`).
- Keep root clean: only repository/system files may exist there.

## Session Memory

- In every working session, maintain durable memory of what the user and agent discussed, decided, changed, verified, and left pending.
- Use one repository-wide memory file: `WORK_LOG.md`.
- Update `WORK_LOG.md` during every session before moving on or stopping.
- Structure the log by session date/time and topic, including what we worked on, key decisions, completed steps, pending tasks, blockers, commands run, and important files or links.
- Before continuing work in a later session, read `WORK_LOG.md` first and use it as the source of continuity for all work in this repository.
- Do not rely only on chat history for continuity.

## Repository Workflows

- Use Python 3.12+ with `PYTHONPATH=src` for local module execution unless the package is installed editable.
- Main CLI entrypoint: `python -m agent_codex.apps.cli.main <command> --project-root .`; installed script name is `agent-codex`.
- Useful runtime checks: `doctor --json`, `metrics --json`, `memory --json`, `tasks --json`, and `task-maintain --once --json`.
- Marketplace workflow: run `marketplace-watch --sample-data --headless` for a local headless sample run; add `--notify-telegram` only when Telegram settings are configured.
- TN VED UI catalog workflow can be run through either `python -m agent_codex.apps.cli.main wb-tnved-ui-catalog --project-root . --json` or `python -m agent_system.cli --project-root . --wb-tnved-ui-catalog --json`.
- Sales workbook commands are `sales-sheet-init`, `sales-sheet-refresh`, and `sales-sheet-diagnose`; use `--scope all|wb|site` with refresh when narrowing the update.

## Validation Commands

- Tests: `python -m pytest tests -v`.
- Lint: `ruff check src tests`.
- Format check: `ruff format --check src tests`.
- Type check: `mypy src/agent_codex`.
- Pre-commit is configured for Ruff auto-fix/format and mypy; run `pre-commit run --all-files` when hooks are installed.

## Generated And Runtime Artifacts

- Treat `.agent_codex/`, `generated/`, and project `runtime/` or `data/` folders as runtime/generated areas; do not edit or commit their contents unless the task explicitly requires it.
- Put ad hoc exports, samples, and temporary files in the relevant project/task folder instead of the repository root.
