from __future__ import annotations

from dataclasses import dataclass, field


PROTECTED_FILE_MARKERS = (
    ".env",
    ".git/config",
    ".git-credentials",
    "id_rsa",
    "id_ed25519",
)


@dataclass(slots=True)
class PolicyDecision:
    allowed: bool
    risk: str
    explanation: str
    matched_rules: list[str] = field(default_factory=list)


def evaluate_tool_action(
    tool_name: str,
    *,
    target_path: str | None = None,
    scratchpad_root: str | None = None,
) -> PolicyDecision:
    matched: list[str] = []
    if target_path:
        normalized = target_path.replace("\\", "/").lower()
        if "../" in normalized or "..\\" in target_path:
            return PolicyDecision(
                allowed=False,
                risk="high",
                explanation="Путь содержит попытку выхода за пределы рабочей директории.",
                matched_rules=["path-traversal"],
            )
        if scratchpad_root:
            scratch_normalized = scratchpad_root.replace("\\", "/").lower()
            if normalized.startswith(scratch_normalized):
                matched.append("scratchpad-allow")
                return PolicyDecision(
                    allowed=True,
                    risk="low",
                    explanation="Доступ к scratchpad разрешён для межагентного обмена.",
                    matched_rules=matched,
                )
        for marker in PROTECTED_FILE_MARKERS:
            if marker.lower() in normalized:
                matched.append("protected-file")
                return PolicyDecision(
                    allowed=False,
                    risk="high",
                    explanation="Файл относится к защищённым конфигурациям или секретам.",
                    matched_rules=matched,
                )
    if tool_name in {"shell", "write_file"}:
        return PolicyDecision(
            allowed=True,
            risk="medium",
            explanation="Действие может менять систему или файлы. Нужна осознанная проверка результата.",
            matched_rules=matched,
        )
    return PolicyDecision(
        allowed=True,
        risk="low",
        explanation="Риск действия низкий.",
        matched_rules=matched,
    )
