from __future__ import annotations

from pathlib import Path


def list_bundled_skills(project_root: str | Path) -> list[str]:
    root = Path(project_root).resolve() / "skills" / "bundled"
    if not root.exists():
        return []
    return sorted(path.parent.name for path in root.glob("*/SKILL.md"))
