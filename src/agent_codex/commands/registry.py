from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    description: str


COMMANDS = [
    CommandSpec("doctor", "Проверить конфиг, layout и подключение адаптеров."),
    CommandSpec("memory", "Показать индекс памяти и при необходимости запустить consolidation."),
    CommandSpec("review", "Проверить текст на violations synthesis rules."),
    CommandSpec("tasks", "Показать текущие runtime task files."),
    CommandSpec("hooks", "Проверить, как policy оценит действие или путь."),
    CommandSpec("compact", "Сжать длинный текст до короткой управленческой сводки."),
    CommandSpec("marketplace-watch", "Построить marketplace watch и headless envelope."),
    CommandSpec("study-digest", "Подготовить краткий digest учебного текста."),
    CommandSpec("telegram-bot", "Запустить Telegram ingress на long polling для асинхронных задач."),
]
