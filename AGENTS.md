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
