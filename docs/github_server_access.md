# GitHub-доступ для VPS

На VPS уже создан отдельный SSH-ключ для GitHub:

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJBFFgTGIIrOCuR0LsUiQDzunLu5qMrpfROzBYbHyGcY openclaw-server
```

Приватный ключ хранится на сервере в:

```text
~/.ssh/github_openclaw_ed25519
```

Что нужно сделать один раз в GitHub:
1. Открыть `Settings`.
2. Перейти в `SSH and GPG keys`.
3. Добавить public key выше.

После этого VPS сможет:
- клонировать приватные репозитории по SSH;
- делать `git pull` и `git fetch`;
- давать OpenClaw доступ к рабочим каталогам с репозиториями.

Проверка после добавления ключа:

```bash
ssh -T git@github.com
git ls-remote git@github.com:burmistrov1337/Agent_Codex.git
git ls-remote git@github.com:burmistrov1337/Agent_Codex_vNext.git
```

Рекомендуемый каталог на VPS:

```bash
mkdir -p ~/git
cd ~/git
git clone git@github.com:burmistrov1337/Agent_Codex.git
git clone git@github.com:burmistrov1337/Agent_Codex_vNext.git
```

Если GitHub потребует подтверждение доступа через браузер, это нормальный шаг для первой привязки ключа. После этого всё будет работать без ручного логина.
