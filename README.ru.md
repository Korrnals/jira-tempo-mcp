# jira-tempo-mcp

![banner](docs/assets/banner.svg)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](#лицензия)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue.svg)](https://github.com/Korrnals/jira-tempo-mcp/pkgs/container/jira-tempo-mcp)

MCP-сервер для **самохостинг-инстанса Jira (Server / Data Center) + Tempo Timesheets 4**.
Учитывайте время, просматривайте worklog'и и создавайте еженедельные отчёты —
всё из вашего AI-агента (Copilot, Claude и др.) через Model Context Protocol.

> 📖 **English version:** [README.md](README.md)

## 📚 Документация

| Документ | Описание |
|----------|---------|
| [API-справочник](docs/api.ru.md) | Полное описание MCP-инструментов с параметрами и примерами |
| [Установка](docs/installation.ru.md) | Установка и настройка |
| [Конфигурация](docs/configuration.ru.md) | Переменные окружения |
| [Отчёты](docs/reports.ru.md) | Форматы отчётов (txt, md, json) и шаблоны |
| [Архитектура](docs/architecture.ru.md) | Архитектура проекта и проектные решения |
| [CLI](docs/cli.ru.md) | Командная строка |
| [Решение проблем](docs/troubleshooting.ru.md) | Частые проблемы и решения |
| [MCP-интеграция](docs/mcp-integration.ru.md) | Интеграция с MCP-клиентами (VS Code и др.) |
| [Развёртывание](docs/deployment.ru.md) | Docker и варианты развёртывания |

---

## 📋 Возможности

| Инструмент | Что делает |
| --- | --- |
| `list_worklogs` | Список worklog'ов Tempo за период или один день |
| `get_worklog` | Получить один worklog по Tempo ID |
| `create_worklog` | Учесть время на задаче Jira с комментарием |
| `delete_worklog` | Удалить worklog (отмена неправильно учтённого времени) |
| `get_issue` | Получить метаданные задачи Jira (summary, статус, проект) |
| `list_favorite_issues` | Список избранных задач текущего пользователя |
| `search_users` | Поиск пользователей Jira по имени, фамилии или username |
| `list_user_tasks` | Задачи пользователя со статусом, приоритетом, комментариями |
| `generate_weekly_report` | Сгенерировать еженедельный отчёт (txt/md/json) из worklog'ов Tempo |
| `generate_team_report` | Сгенерировать командный отчёт (txt/md/json) для нескольких пользователей |
| `generate_tasks_report` | Сгенерировать отчёт по задачам (md/txt/json) с группировкой по статусам |
| `list_report_templates` | Показать доступные шаблоны отчётов (встроенные + кастомные) |

Начиная с v0.2.0 сервер поддерживает **командные отчёты** (агрегация по
пользователям с rate-limiting) и **кастомные шаблоны отчётов** (Jinja2-песочница
+ opt-in Python). Начиная с v0.3.0 все генераторы отчётов поддерживают **три
формата вывода**: `txt` (plain text), `md` (Markdown с таблицами и эмодзи) и
`json` (структурированный JSON). Подробнее — в [docs/reports.ru.md](docs/reports.ru.md).

Полный справочник инструментов с параметрами и примерами — в [docs/api.ru.md](docs/api.ru.md).

---

## 🚀 Быстрый старт

Запуск меньше чем за минуту:

**Установка одной командой:**

```bash
curl -fsSL https://raw.githubusercontent.com/Korrnals/jira-tempo-mcp/main/scripts/install.sh | bash
```

Скрипт скачивает и запускает интерактивный установщик, который:

- ✅ Проверяет Python 3.11+ и pip
- ✅ Клонирует репозиторий и создаёт venv
- ✅ Устанавливает пакет
- ✅ Проводит через настройку учётных данных Jira
- ✅ Регистрирует MCP-сервер в VS Code (user + workspace)

> 💡 **Совет:** Установщик не требует `sudo` — всё ставится в user space.
> Скрипт идемпотентен: повторный запуск обновляет без затирания существующего конфига.

**Удаление:**

```bash
curl -fsSL https://raw.githubusercontent.com/Korrnals/jira-tempo-mcp/main/scripts/install.sh | bash -- --uninstall
```

**Docker:**

```bash
docker run -i --rm -e JIRA_PAT="$JIRA_PAT" ghcr.io/korrnals/jira-tempo-mcp:latest
```

> ⚠️ **Внимание:** URL установочного скрипта заработает, когда репозиторий
> станет публичным. До этого — клонируйте вручную и запустите `python install.py`.

---

### 🔧 Из исходников (разработка)

Интерактивный установщик создаёт venv, записывает `.env`, регистрирует
MCP-сервер в VS Code и опционально проверяет связь с Jira:

```bash
cd jira-tempo-mcp
python install.py
```

Или установка из исходников:

```bash
git clone https://github.com/Korrnals/jira-tempo-mcp.git
cd jira-tempo-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
jira-tempo-mcp serve
```

Или запуск через Docker:

```bash
docker run -i --rm \
  --env-file .env \
  ghcr.io/korrnals/jira-tempo-mcp:latest
```

Все способы установки: [docs/installation.ru.md](docs/installation.ru.md).

---

## ⚙️ Настройка

Вся конфигурация — через переменные окружения. Обязательные:

| Переменная | Описание |
| --- | --- |
| `JIRA_BASE_URL` | Базовый URL Jira без слэша на конце |
| `JIRA_USER` | Имя пользователя Jira (логин) |
| `JIRA_PAT` | Personal Access Token — **никогда не коммитьте** |

Опциональные: `JIRA_TIMEZONE`, `TEMPO_API_TOKEN`, `LOG_LEVEL`,
`JIRA_HTTP_TIMEOUT` и переменные отчёта (`REPORT_*`).

Полный справочник: [docs/configuration.ru.md](docs/configuration.ru.md).

---

## 🔌 MCP-интеграция

Сервер работает через **stdio** и регистрируется в VS Code `mcp.json`:

```json
{
  "servers": {
    "jira-tempo": {
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["-m", "jira_tempo_mcp.server"],
      "envFile": "/home/your-username/.config/Code/User/.env.local",
      "env": {
        "JIRA_BASE_URL": "https://jira.example.com",
        "JIRA_USER": "your-username",
        "PYTHONPATH": "${workspaceFolder}/src"
      }
    }
  }
}
```

> 💡 **Совет:** Всегда используйте **абсолютные пути** для `envFile` — `~` не
> работает в sandbox-окружениях (distrobox, snap, контейнеры).

Полное руководство: [docs/mcp-integration.ru.md](docs/mcp-integration.ru.md).

---

## 🖥️ CLI

```text
jira-tempo-mcp                  # запустить MCP-сервер (по умолчанию)
jira-tempo-mcp serve            # запустить MCP-сервер
jira-tempo-mcp install          # интерактивный установщик
jira-tempo-mcp uninstall        # откатить установку
jira-tempo-mcp --version        # показать версию
```

Полный справочник: [docs/cli.ru.md](docs/cli.ru.md).

---

## 🔒 Безопасность

- **🔑 Токены не покидают локальный процесс** — `JIRA_PAT` отправляется только
  на инстанс Jira через HTTPS.
- **🛡️ TLS-верификация всегда включена**, **HTTP-редиректы отключены**
  (`follow_redirects=False`) — предотвращает утечку PAT через редирект.
- **👁️ Токены замаскированы в логах** — `Config.__repr__` заменяет `JIRA_PAT` на `***`.
- **✅ Валидация ввода** — ключи задач, даты и `output_dir` (защита от path
  traversal) проверяются перед любым вызовом API.
- **🐳 Docker** — многостадийная сборка, non-root пользователь, секреты никогда
  не вшиваются в образ.

Полная модель: [docs/architecture.ru.md#безопасность](docs/architecture.ru.md#безопасность).

## 🛠️ Разработка

Канонический quality gate для этого репозитория — локальный набор `make`.
GitHub Actions в этом репозитории намеренно отключены, поэтому `make ci` —
это то, что каждое изменение должно пройти перед мержем: линтер, тайпчекер,
тесты и сборку одной командой.

```sh
make ci         # полный quality gate — lint + typecheck + test + build
make lint       # ruff
make typecheck  # mypy
make test       # pytest
make build      # python -m build (sdist + wheel)
```

---

##  Лицензия

MIT
