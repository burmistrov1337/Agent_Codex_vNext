# Agent_Codex vNext

Чистый репозиторий следующей итерации `Agent_Codex`, сфокусированный на локальном runtime, CLI и прикладных доменах без старого серверного слоя.

## Что это за версия

`vNext` нужен как более аккуратная основа для:

- локальной агентной работы через CLI;
- явных runtime-контрактов, hooks и task lifecycle;
- памяти, журналов сессий и артефактов в `.agent_codex/`;
- прикладных доменов вроде marketplace и sales workbook;
- подключения разных LLM backend без жёсткой привязки к одному провайдеру.

## Быстрый локальный старт

```powershell
cd D:\Agent_Codex_vNext
$env:PYTHONPATH='src'
python -m agent_codex.apps.cli.main doctor --json
python -m agent_codex.apps.cli.main metrics --json
python -m agent_codex.apps.cli.main marketplace-watch --sample-data --headless
python -m playwright install chromium
python -m agent_system.cli --project-root . --wb-tnved-ui-catalog --json
```

## Основные команды

- `doctor` — проверить конфиг, layout и доступность поверхностей.
- `metrics` — собрать краткую runtime-диагностику по памяти, задачам, артефактам и backend.
- `memory` — посмотреть индекс памяти и при необходимости запустить consolidation.
- `tasks` — посмотреть текущие task-файлы runtime.
- `task-maintain` — прогнать maintenance-цикл для TaskBus.
- `marketplace-watch` — собрать headless marketplace-run с артефактами.
- `sales-sheet-*` — работать с sales workbook.
- `telegram-bot` — локальный Telegram ingress, если он нужен в этой ветке.

## Переменные окружения

Базовый набор в `.env.example` покрывает:

- Telegram ingress;
- Wildberries;
- Google Sheets и AdvantShop для sales-домена;
- backend-конфигурацию для `deterministic`, `null`, `groq`, `openai`, `anthropic`, `ollama`;
- runtime paths в `.agent_codex/`.

## Структура runtime

По умолчанию runtime пишет данные в:

- `.agent_codex/memory/` — topics, logs и consolidation state;
- `.agent_codex/sessions/` — сессионные события;
- `.agent_codex/tasks/` — task bus envelopes;
- `.agent_codex/artifacts/` — generated artifacts и run envelopes.

## Документация

- `docs/migration_matrix.md` — что в `vNext` уже перенесено, а что ещё нет;
- `docs/claude_gap_target_spec.md` — архитектурный gap-analysis относительно более сильных агентных систем.
