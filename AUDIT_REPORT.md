![1775805751443](image/AUDIT_REPORT/1775805751443.png)![1775806124803](image/AUDIT_REPORT/1775806124803.png)![1775806506379](image/AUDIT_REPORT/1775806506379.png)# Agent_Codex_vNext — Архитектурный аудит и план улучшений

> Дата: 2026-04-10
> Аудитор: Claude Opus 4.6
> Статус: Готов к выполнению

---

## Executive Summary

Проект **Agent_Codex_vNext** — это зрелый MVP агентной системы с Telegram-ингрессом, marketplace-мониторингом (Wildberries), sales-панелью (Google Sheets + AdvantShop), memory-подсистемой и hooks/safety pipeline. Код чистый, хорошо структурирован, тесты покрывают ключевые сценарии.

**Сильные стороны:**
- Чистая модульная архитектура с явными контрактами
- File-based TaskBus с leases, retry, heartbeat — работает
- Telegram-бот с confirm/reject, dedup, self-check — production-ready MVP
- Marketplace vertical — глубокая интеграция с WB API, красивые дашборды
- Sales domain — полноценная экономика, формулы, Google Sheets интеграция
- 22 unit-теста покрывают основные сценарии
- Hooks pipeline с policy decisions и audit log

**Критические проблемы:**
- Нет CI/CD, linting, type checking
- Зависимости не pinned, нет lock-файла
- LLM backend — только Groq, нет Anthropic/OpenAI
- Нет async/await — всё синхронное
- Memory consolidation — примитивная, без LLM-экстракции
- Нет observability (metrics, tracing, structured logging)

---

## P0 — Критические (блокируют production)

### 1. Добавить CI/CD и code quality pipeline

**Проблема:** Нет линтинга, type checking, авто-тестов. Проект не может гарантировать качество при изменениях.

**Что сделать:**
- Добавить `ruff` (lint + format) в `pyproject.toml`
- Добавить `mypy` для type checking
- Создать `.github/workflows/ci.yml` с шагами: lint → typecheck → test
- Добавить `pre-commit` hook для локальной проверки

**Файлы:** `pyproject.toml`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml`

**Приоритет:** P0 — без этого любой коммит может сломать продакшн

---

### 2. Pin dependencies и добавить lock-файл

**Проблема:** В `pyproject.toml` только 2 зависимости (`google-auth`, `requests`), но код импортирует `reportlab` (PDF), который не declared. Нет lock-файла — билды не воспроизводимы.

**Что сделать:**
- Добавить все runtime зависимости в `pyproject.toml`:
  - `reportlab` (опциональная, для PDF)
  - `google-auth` (уже есть)
  - `requests` (уже есть)
- Добавить optional dependency groups:
  - `[project.optional-dependencies]` → `pdf = ["reportlab"]`, `dev = ["pytest", "ruff", "mypy"]`
- Использовать `uv` или `pip-tools` для lock-файла

**Файлы:** `pyproject.toml`

---

### 3. Добавить structured logging

**Проблема:** Вся диагностика идёт через `print()` и `daily_log`. В production это неприемлемо — нет уровней, нет structured output, нет correlation IDs.

**Что сделать:**
- Создать `src/agent_codex/logging.py` с `structlog` или стандартным `logging`
- Заменить все `print()` в CLI на logger
- Добавить `request_id` / `run_id` в каждый log entry
- Log format: JSON для production, human-readable для dev

**Файлы:** `src/agent_codex/logging.py` (новый), все файлы с `print()`

---

## P1 — Важные (улучшают надёжность и расширяемость)

### 4. Расширить LLM backends

**Проблема:** Поддерживается только Groq. Нет Anthropic Claude, OpenAI, Ollama (local). `pyproject.toml` не declares `google-auth` как required для Google Sheets.

**Что сделать:**
- Добавить `AnthropicBackendAdapter` (Claude API)
- Добавить `OpenAIBackendAdapter` (GPT-4/4o)
- Добавить `OllamaBackendAdapter` (local, бесплатный)
- Рефакторинг `select_backend()` → factory pattern с registry
- Добавить env vars: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OLLAMA_BASE_URL`

**Файлы:** `src/agent_codex/integrations/llm.py`, `.env.example`, `src/agent_codex/config.py`

---

### 5. Перевести на async/await

**Проблема:** Весь код синхронный. Telegram polling блокирует поток. HTTP-запросы к WB, Google, AdvantShop — все sync. Это ограничивает throughput и не позволяет параллельные запросы.

**Что сделать:**
- Перевести `telegram_raw.py` на `aiohttp` + `asyncio`
- Перевести `AgentExecutor.run_request()` на async
- Перевести все API клиенты на async
- Использовать `asyncio.gather()` для параллельных worker executions
- **Важно:** Это большой рефакторинг — делать поэтапно, начиная с Telegram

**Файлы:** Практически все файлы в `integrations/`, `runtime/`

---

### 6. Улучшить Memory Consolidation

**Проблема:** Consolidation просто склеивает последние 7 логов в один topic. Нет LLM-экстракции, нет дедупликации, нет stale topic cleanup.

**Что сделать:**
- Добавить LLM-powered extraction: summarization через backend
- Добавить stale topic detection (topics старше N дней без обновлений)
- Добавить topic merging при overlap
- Добавить memory search (full-text или embedding-based)
- Добавить `forget` policy для старых данных

**Файлы:** `src/agent_codex/memory/consolidation.py`

---

### 7. Добавить Observability

**Проблема:** Нет метрик, tracing, health metrics beyond `doctor`. Невозможно мониторить production.

**Что сделать:**
- Добавить Prometheus metrics endpoint (или простой JSON metrics)
- Метрики: task count by status, avg execution time, error rate, API latency
- Добавить `metrics` команду в CLI
- Интегрировать с Docker healthcheck
- Добавить Grafana dashboard template

**Файлы:** `src/agent_codex/runtime/metrics.py` (новый), `docker-compose.yml`

---

### 8. Добавить Background Task Scheduler

**Проблема:** Нет встроенного scheduler. `marketplace-watch` запускается только вручную или через n8n. Sales sheet refresh cron declared но не implemented.

**Что сделать:**
- Добавить `APScheduler` или `croniter`-based scheduler
- Scheduled jobs: sales-sheet-refresh, marketplace-watch, memory-consolidation
- Добавить `scheduler` команду в CLI
- Интегрировать с TaskBus для durable execution

**Файлы:** `src/agent_codex/runtime/scheduler.py` (новый)

---

## P2 — Улучшения архитектуры

### 9. Tool Registry с валидацией

**Проблема:** `tools/base.py` — только dataclass без функциональности. Нет tool discovery, validation, schema layer.

**Что сделать:**
- Создать `ToolRegistry` с register/discover
- Добавить JSON Schema для каждого tool input/output
- Добавить tool policy metadata (risk, required_permissions)
- Добавить tool execution tracing

**Файлы:** `src/agent_codex/tools/base.py`, `src/agent_codex/tools/registry.py` (новый)

---

### 10. Event Bus для межмодульной коммуникации

**Проблема:** Модули вызывают друг друга напрямую. Нет event-driven архитектуры. Hooks pipeline — шаг в правильном направлении, но ограничен.

**Что сделать:**
- Создать простой event bus (in-memory, file-backed)
- Events: `task.created`, `task.completed`, `artifact.generated`, `memory.updated`
- Подписчики: memory, hooks, metrics, n8n notifier
- Это позволит добавить новые реакции без изменения core

**Файлы:** `src/agent_codex/runtime/event_bus.py` (новый)

---

### 11. Configuration Validation

**Проблема:** `load_settings()` молча принимает любые значения. Нет валидации, нет warnings о missing required fields.

**Что сделать:**
- Добавить валидацию с чёткими error messages
- Required vs optional fields
- Cross-field validation (e.g., если Google Sheets configured — service account required)
- `doctor` команда должна показывать конкретные missing config items

**Файлы:** `src/agent_codex/config.py`

---

### 12. Error Handling Strategy

**Проблема:** Разные стили обработки ошибок: где-то `RuntimeError`, где-то custom exceptions, где-то bare `except Exception`. Нет единой стратегии.

**Что сделать:**
- Создать иерархию exceptions: `AgentCodexError` → `ConfigError`, `ApiError`, `TaskError`, `MemoryError`
- Добавить retry decorator с exponential backoff
- Добавить circuit breaker для внешних API
- Стандартизировать error responses во всех CLI командах

**Файлы:** `src/agent_codex/errors.py` (новый), все файлы с error handling

---

## P3 — Улучшения developer experience

### 13. Расширить тестовое покрытие

**Проблема:** 22 теста покрывают основные сценарии, но нет coverage для:
- LLM backend adapters
- Google Sheets client
- AdvantShop client
- Wildberries API client
- Synthesizer
- HookPipeline
- ConsolidationEngine (полностью)
- CLI commands (все)

**Что сделать:**
- Добавить тесты для всех integrations (mock HTTP)
- Добавить integration tests для full request → response cycle
- Добавить property-based tests для economics calculations
- Target: 80%+ coverage

**Файлы:** `tests/`

---

### 14. Docker Hardening

**Проблема:**
- Dockerfile копирует `.env.example` в образ (information leak)
- Нет `.dockerignore`
- Нет non-root user в контейнере
- Нет multi-stage build
- n8n использует `latest` tag

**Что сделать:**
- Создать `.dockerignore`
- Multi-stage build для меньшего образа
- Non-root user
- Pin n8n version
- Healthcheck должен проверять не только doctor но и connectivity

**Файлы:** `Dockerfile`, `.dockerignore` (новый), `docker-compose.yml`

---

### 15. Documentation Updates

**Проблема:**
- `claude_gap_target_spec.md` устарел — TaskBus уже реализован, Synthesizer уже есть
- Нет API documentation
- Нет contributing guide
- Нет changelog

**Что сделать:**
- Обновить `claude_gap_target_spec.md` — перенести Done из "Needs Extension" в "Done"
- Добавить `docs/architecture.md` с диаграммой компонентов
- Добавить `CONTRIBUTING.md`
- Добавить `CHANGELOG.md`

**Файлы:** `docs/`, `CONTRIBUTING.md`, `CHANGELOG.md`

---

## P4 — Nice to have

### 16. Web UI Dashboard

Простой Flask/FastAPI сервер с веб-интерфейсом для:
- Просмотр task status
- Просмотр memory
- Запуск команд
- Просмотр artifacts

### 17. Multi-bot Support

Поддержка нескольких Telegram ботов из одного инстанса.

### 18. Plugin System

Формализовать `skills/bundled/` как полноценную plugin систему с lifecycle hooks.

### 19. Database Backend

Заменить file-based storage на SQLite для лучшей консистентности и query capabilities.

### 20. Rate Limiting

Rate limiting для всех внешних API (WB, Google, AdvantShop) с token bucket.

---

## Сводная таблица приоритетов

| # | Задача | Приоритет | Сложность | Файлы |
|---|--------|-----------|-----------|-------|
| 1 | CI/CD + code quality | P0 | Низкая | 3-4 |
| 2 | Pin dependencies | P0 | Низкая | 1-2 |
| 3 | Structured logging | P0 | Средняя | 5-8 |
| 4 | Расширить LLM backends | P1 | Средняя | 3-4 |
| 5 | Async/await migration | P1 | Высокая | 15+ |
| 6 | Memory consolidation | P1 | Средняя | 2-3 |
| 7 | Observability | P1 | Средняя | 3-4 |
| 8 | Background scheduler | P1 | Средняя | 2-3 |
| 9 | Tool Registry | P2 | Средняя | 3-4 |
| 10 | Event Bus | P2 | Средняя | 2-3 |
| 11 | Config validation | P2 | Низкая | 1-2 |
| 12 | Error handling strategy | P2 | Средняя | 5-8 |
| 13 | Test coverage | P3 | Средняя | 8-10 |
| 14 | Docker hardening | P3 | Низкая | 3-4 |
| 15 | Documentation | P3 | Низкая | 4-5 |

---

## Рекомендованный порядок выполнения

**Wave 1 (Foundation):** 1 → 2 → 3 → 11 → 12
**Wave 2 (Reliability):** 4 → 6 → 7 → 8 → 13
**Wave 3 (Architecture):** 9 → 10 → 14 → 15
**Wave 4 (Scale):** 5 → 16 → 17 → 18 → 19 → 20

Каждая волна должна завершаться passing CI pipeline и всеми passing тестами.
