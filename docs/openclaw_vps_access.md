# OpenClaw на VPS

## Что поднято

OpenClaw развернут на сервере как отдельный стек в `/opt/openclaw`.

- основной сервис: `openclaw-gateway`
- Control UI доступен только локально на сервере
- для входа с Windows используется SSH-туннель
- Telegram подключен как канал
- AI-backend пока не настроен, поэтому без внешнего model provider OpenClaw не считается рабочим чат-ассистентом

## Как открыть Control UI с Windows

1. Подними туннель:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Agent_Codex_vNext\scripts\start_openclaw_ui_tunnel.ps1
```

2. Оставь окно `ssh.exe` открытым.

3. Открой в браузере:

```text
http://127.0.0.1:18789
```

Или запусти оба шага сразу:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Agent_Codex_vNext\scripts\open_openclaw_ui.ps1
```

## Что сделать в UI

1. Зайти в Control UI.
2. При необходимости вставить gateway token.
3. Проверить, что gateway жив.
4. Проверить, что Telegram-канал включен.

## Полезные команды на сервере

```bash
cd /opt/openclaw
docker compose ps
docker compose logs --tail=100 openclaw-gateway
docker compose run --rm --no-deps openclaw-cli status all
docker compose run --rm --no-deps openclaw-cli doctor
```

## Ограничение текущего этапа

OpenClaw сейчас поднят как инфраструктура:

- gateway
- Control UI
- Telegram-канал

Но без внешнего model provider он не будет давать полноценные AI-ответы. Это ожидаемое состояние, а не скрытая поломка.
