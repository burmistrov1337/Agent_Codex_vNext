## Промт для Codex (Wave 1: Foundation)

```markdown
Codex — Wave 1: Foundation

Проект: Agent_Codex_vNext (d:\Agent_Codex_vNext)
Контекст: прочитай AUDIT_REPORT.md

Выполни 5 задач. После каждой — убедись что существующие тесты проходят.

## Задача 1: CI/CD + Code Quality

1. В `pyproject.toml` добавь в конец:
```toml
[project.optional-dependencies]
dev = ["ruff>=0.9", "mypy>=1.14", "pytest>=8.3", "pytest-cov>=6.0"]
pdf = ["reportlab>=4.2"]

[tool.ruff]
target-version = "py312"
line-length = 120
[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF"]
ignore = ["E501"]
[tool.ruff.lint.isort]
known-first-party = ["agent_codex"]

[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
check_untyped_defs = true
no_implicit_optional = true
[[tool.mypy.overrides]]
module = ["google.*", "reportlab.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
```

2. Создай `.github/workflows/ci.yml` с jobs: lint (ruff check + format), typecheck (mypy), test (pytest)
3. Создай `.pre-commit-config.yaml` с ruff + mypy
4. Запусти: `pip install -e ".[dev]" && ruff check src/ tests/ --fix && ruff format src/ tests/`

## Задача 2: Docker Hardening

1. Создай `.dockerignore` (исключи: __pycache__, .env, .agent_codex, .docker, .git, tests/, *.md кроме README.md)
2. Обнови `Dockerfile`: убери COPY .env.example, добавь non-root user (agentcodex), не копируй deploy/
3. В `docker-compose.yml` замени n8n `latest` на `1.76.0`

## Задача 3: Structured Logging

1. Создай `src/agent_codex/logging_config.py` с функциями `setup_logging()` и `get_logger()`
2. В `main()` (apps/cli/main.py) добавь `setup_logging(log_file=settings.runtime_root / "agent.log")` после load_settings

## Задача 4: Configuration Validation

1. В `config.py` добавь метод `validate()` в Settings — возвращает список missing required fields
2. В `doctor_report()` (executor.py) добавь `"config_issues": self.settings.validate()`

## Задача 5: Error Handling

1. Создай `src/agent_codex/errors.py` с иерархией: AgentCodexError → ConfigError, ApiError, TaskError, MemoryStoreError, StorageError
2. Обнови exceptions:
   - telegram_raw.py: TelegramNotifyError(ApiError)
   - google_sheets.py: GoogleSheetsError(ApiError)
   - advantshop.py: AdvantShopApiError(ApiError)
   - marketplace/api.py: WildberriesApiError(ApiError)
   - sales/service.py: SalesSheetConfigurationError(ConfigError)

## Финальная проверка

- ruff check src/ tests/ — чисто
- ruff format --check src/ tests/ — чисто
- mypy src/agent_codex/ — без ошибок
- pytest tests/ -v — все проходят
- doctor --json — работает с config_issues
