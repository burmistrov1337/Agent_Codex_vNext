from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    description: str


COMMANDS = [
    CommandSpec("doctor", "Проверить конфиг, layout и подключение адаптеров."),
    CommandSpec("metrics", "Показать runtime-метрики и состояние backend-контуров."),
    CommandSpec("memory", "Показать индекс памяти и при необходимости запустить consolidation."),
    CommandSpec("review", "Проверить текст на violations synthesis rules."),
    CommandSpec("tasks", "Показать текущие runtime task files."),
    CommandSpec("task-maintain", "Запустить maintenance цикл для task bus."),
    CommandSpec("hooks", "Проверить, как policy оценит действие или путь."),
    CommandSpec("compact", "Сжать длинный текст до короткой управленческой сводки."),
    CommandSpec("marketplace-watch", "Построить marketplace watch и headless envelope."),
    CommandSpec("wb-tnved-ui-catalog", "Собрать каталог ТН ВЭД из UI WB по нашим категориям."),
    CommandSpec("sales-sheet-init", "Инициализировать sales workbook поверх интеграций."),
    CommandSpec("sales-sheet-refresh", "Обновить sales workbook (all/wb/site)."),
    CommandSpec("sales-sheet-diagnose", "Диагностика состояния sales workbook контура."),
    CommandSpec("telegram-bot", "Локальный polling ingress для Telegram задач."),
    CommandSpec("study-digest", "Подготовить краткий digest учебного текста."),
]
