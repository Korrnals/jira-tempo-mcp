# 🖥️ Справочник CLI

Консольный скрипт `jira-tempo-mcp` переключает между MCP-сервером,
интерактивным установщиком, деинсталлятором, командой самообновления и
установщиком специалиста.

---

## 🖥️ Команды

```text
jira-tempo-mcp                  # запустить MCP-сервер (по умолчанию = serve)
jira-tempo-mcp serve            # запустить MCP-сервер (stdio)
jira-tempo-mcp install          # интерактивный установщик (venv + .env + VS Code)
jira-tempo-mcp uninstall        # откатить установку
jira-tempo-mcp update           # самообновление установленного пакета
jira-tempo-mcp install-specialist  # установить skill специалиста в AI-оболочки
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

## � `update`

Самообновляет установленный пакет. Определяет способ установки (по
`direct_url.json` от pip) и выполняет соответствующую процедуру:

| Способ установки | Что выполняется |
| --- | --- |
| Wheel / пакетный индекс (PyPI, wheel-файл, локальная не-editable установка) | `pip install --upgrade jira-tempo-mcp` |
| Editable (`pip install -e .` из git-клона) | `git pull --ff-only` в клоне, затем `pip install -e .` для обновления метаданных |
| Не установлен через pip (Docker-образ, запуск через `PYTHONPATH`) | Не угадывает — печатает подсказку для каждого способа (например, `docker pull ghcr.io/korrnals/jira-tempo-mcp:latest`) и выходит с кодом `1` |

```bash
jira-tempo-mcp update
```

Пример вывода (wheel-установка):

```text
Install mode: wheel — installed from a package index (no direct_url.json)
--> pip install --upgrade jira-tempo-mcp: /path/to/python -m pip install --upgrade jira-tempo-mcp
Update complete.
Version: 0.6.0 -> 0.7.0
If an MCP server (jira-tempo-mcp serve) is running, restart it to pick up the new code.
```

Примечания:

- pip запускается через **текущий интерпретатор** (`sys.executable -m pip`) —
  обновление попадает в то же окружение/venv, из которого вызвали `update`.
- Ошибка любого шага прерывает обновление — больше ничего не меняется; код
  выхода `1`.
- Не принимает флагов; неизвестный флаг завершается с кодом `2`.

---

## 🤖 `install-specialist`

Устанавливает специалиста **JTM: Jira Tempo Reports** в AI-оболочки —
набор устанавливаемых файлов зависит от оболочки (см. таблицу ниже).
Работает идемпотентно: повторная установка
перезаписывает файлы JTM, предварительно создавая резервную копию
(`~/.copilot/.backups/<name>.bak.YYYYMMDD-HHMMSS` — вне каталогов оболочки,
каталоги оболочки остаются чистыми); чужие файлы не затрагиваются.
Обратимо через `--remove`, который также вычищает остатки старых установок
(JTM-файлы в `~/.claude/agents/`, резервные копии `.bak.*` рядом с файлами
JTM).

### 🔧 Флаги

| Флаг | Эффект |
| --- | --- |
| `--harness NAME` | Установить только в указанную оболочку; флаг повторяемый (`--harness copilot --harness claude`); по умолчанию: все поддерживаемые (неподдерживаемые пропускаются с явной причиной) |
| `--list` | Показать статус поддержки всех зарегистрированных оболочек и выйти |
| `--remove` | Удалить специалиста из выбранных оболочек (по умолчанию: из всех); удаляет только файлы JTM; если удалять нечего, печатает «nothing to remove — already clean»; также вычищает остатки старых установок (JTM-файлы в `~/.claude/agents/`, резервные копии `.bak.*`) и печатает их количество |

`--harness`, `--list` и `--remove` взаимоисключающие. Неизвестые имена
оболочек отклоняются до любой записи.

### 🧩 Поддержка оболочек

| Оболочка | Статус | Устанавливаемые файлы |
| --- | --- | --- |
| `copilot` | ✅ поддерживается | `~/.copilot/agents/jtm-jira-tempo-reports.agent.md`, `~/.copilot/skills/jira-tempo-reports/` (`SKILL.md` + `JTM_AGENT.md`) |
| `claude` | ✅ поддерживается | `~/.claude/skills/jira-tempo-reports/` (`SKILL.md` + `JTM_AGENT.md`) — только каталог skills, без файла агента (VS Code кросс-сканирует каталог агентов claude и показывает дублирующуюся запись в picker) |
| `opencode` | ✅ поддерживается | `~/.config/opencode/skills/jira-tempo-reports/` (`SKILL.md` + `JTM_AGENT.md`) — только каталог skills |
| `codex` | ⏭️ пропускается | не поддерживается: нет конвенции файлов агента — `AGENTS.md` управляется системой, безопасная ручная установка не определена |

Фактический вывод `--list`:

```text
Supported harnesses:
  copilot    supported                                               VS Code Copilot Chat (agents + skills)
  claude     supported                                               Claude Code (skills directory)
  opencode   supported                                               OpenCode (skills directory)
  codex      skipped — unsupported: no agent-file convention (AGENTS.md is machine-managed; safe manual placement is not defined) OpenAI Codex CLI
```

### 💡 Примеры

```bash
# Установить во все поддерживаемые оболочки (по умолчанию)
jira-tempo-mcp install-specialist

# Только конкретные оболочки
jira-tempo-mcp install-specialist --harness copilot --harness claude

# Показать статус поддержки
jira-tempo-mcp install-specialist --list

# Удалить (из всех, либо выбранных через --harness)
jira-tempo-mcp install-specialist --remove
```

Неизвестное имя оболочки (usage-блок опущен):

```text
jira-tempo-mcp install-specialist: error: unknown harness(es): nonexistent.
Known: claude, codex, copilot, opencode. Use --list to show support status.
```

Работает при установке **из wheel** — интеграционные файлы поставляются внутри
wheel (`jira_tempo_mcp.integration`), git clone не нужен. Прежний интерактивный
`jira-tempo-mcp install` (настройка `.env`) по-прежнему требует git clone;
см. [installation.ru.md](installation.ru.md).

---

## �🗑️ `uninstall`

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
# jira-tempo-mcp 0.6.0

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
python -m jira_tempo_mcp.cli --version # версия через диспетчер
python -m jira_tempo_mcp.cli update    # самообновление
python -m jira_tempo_mcp.cli install-specialist --list
python install.py                      # install
python install.py uninstall            # uninstall
```

---

## 📊 Коды выхода

| Код | Значение |
| --- | --- |
| `0` | ✅ успех |
| `1` | ❌ ошибка подкоманды (установщик/деинсталлятор, `update`, `install-specialist`) |
| `2` | ❌ неизвестная подкоманда, флаг или имя оболочки |

---

## ➡️ Дальнейшие шаги

- 🌐 [api.ru.md](api.ru.md) — MCP-инструменты, которые открывает `serve`
- 📦 [installation.ru.md](installation.ru.md) — пошаговое описание установщика
- ⚙️ [configuration.ru.md](configuration.ru.md) — переменные окружения при запуске
