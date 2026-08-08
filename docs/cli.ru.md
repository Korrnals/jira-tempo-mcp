# 🖥️ Справочник CLI

Консольный скрипт `jira-tempo-mcp` переключает между MCP-сервером,
интерактивным установщиком и деинсталлятором.

---

## 🖥️ Команды

```text
jira-tempo-mcp                  # запустить MCP-сервер (по умолчанию = serve)
jira-tempo-mcp serve            # запустить MCP-сервер (stdio)
jira-tempo-mcp install          # интерактивный установщик (venv + .env + VS Code)
jira-tempo-mcp uninstall        # откатить установку
jira-tempo-mcp --version        # показать версию
jira-tempo-mcp --help           # показать справку
```

---

## 🚀 `serve`

Запускает MCP-сервер через stdio. Читает JSON-RPC из stdin, пишет в stdout,
логи в stderr. Это действие по умолчанию, если подкоманда не указана.

```bash
# внутри venv
jira-tempo-mcp serve

# или через модуль пакета
python -m jira_tempo_mcp.server
```

Сервер читает конфигурацию из переменных окружения / `.env` при запуске.
См. [configuration.ru.md](configuration.ru.md).

---

## 📦 `install`

Запускает интерактивный установщик (`install.py`). Создаёт venv, записывает
`.env`, регистрирует MCP-сервер в VS Code `mcp.json` и опционально проверяет
связь с Jira.

```bash
jira-tempo-mcp install
# эквивалентно:
python install.py
```

Полное описание — в [installation.ru.md](installation.ru.md).

### 🔧 Флаги установщика

Установщик (`install.py`) принимает следующие флаги — полезны в CI, headless-окружениях
или при перезапуске только части настройки:

| Флаг | Эффект |
| --- | --- |
| `-n` / `--non-interactive` / `--yes` | Запуск без запросов; значения берутся из флагов / env-переменных / умолчаний |
| `--register-only` | Пропустить venv/pip — только записать `.env.local` и зарегистрировать в `mcp.json` |
| `--no-agent` | Пропустить установку агента Copilot Chat (по умолчанию агент устанавливается) |
| `--uninstall-agent` | Удалить только агент Copilot Chat + skill + `JTM_AGENT.md`, затем выйти |
| `--skip-vscode` | Пропустить регистрацию в VS Code `mcp.json` (только записать `.env.local`) |
| `--jira-base-url` | Переопределить `JIRA_BASE_URL` (по умолч.: env-переменная) |
| `--jira-user` | Переопределить `JIRA_USER` (по умолч.: env-переменная) |
| `--jira-pat` | Переопределить `JIRA_PAT` (по умолч.: env-переменная) |
| `--jira-timezone` | Переопределить `JIRA_TIMEZONE` (по умолч.: `Europe/Moscow`) |
| `--log-level` | Переопределить `LOG_LEVEL` (по умолч.: `INFO`) |

Пример — только регистрация, неинтерактивно:

```bash
python install.py --non-interactive --register-only
```

---

## 🗑️ `uninstall`

Откатывает установку в 4 шага:

1. ✅ Удалить `jira-tempo` из VS Code `mcp.json` (сначала резервная копия
   `mcp.json.bak`; другие серверы сохраняются).
2. ⚠️ Удалить `.env` — опционально, **по умолчанию: Нет**. Необратимо; требует
   явного подтверждения. Значение PAT не выводится.
3. ⚠️ Удалить pip-пакет из venv — опционально, **по умолчанию: Нет**. Сама
   директория `.venv` сохраняется.
4. ✅ Вывести сводку с дальнейшими шагами.

```bash
jira-tempo-mcp uninstall
```

---

## ℹ️ `--version` / `--help`

```bash
jira-tempo-mcp --version
# jira-tempo-mcp 0.4.1

jira-tempo-mcp --help
# выводит блок использования, показанный выше
```

---

## 🔧 Прямой вызов модуля

Если консольный скрипт не в `PATH` (например, запуск вне venv), вызовите
модуль напрямую:

```bash
python -m jira_tempo_mcp.server        # serve
python -m jira_tempo_mcp               # __main__ диспетчеризует на serve
python install.py                      # install
python install.py uninstall            # uninstall
```

---

## 📊 Коды выхода

| Код | Значение |
| --- | --- |
| `0` | ✅ успех |
| `1` | ❌ ошибка установщика/деинсталлятора (напр. `install.py` не найден) |
| `2` | ❌ неизвестная подкоманда |

---

## ➡️ Дальнейшие шаги

- 🌐 [api.ru.md](api.ru.md) — MCP-инструменты, которые открывает `serve`
- 📦 [installation.ru.md](installation.ru.md) — пошаговое описание установщика
- ⚙️ [configuration.ru.md](configuration.ru.md) — переменные окружения при запуске
