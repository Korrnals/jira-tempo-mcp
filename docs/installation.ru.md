# 📦 Установка

Способы установки `jira-tempo-mcp` — четыре пути: интерактивный установщик,
pip, из исходников, Docker.

---

## 📦 Требования

| Требование | Версия | Примечания |
| --- | --- | --- |
| Python | 3.11+ | рекомендуется 3.12 |
| pip | последняя | входит в комплект Python |
| Jira | Server / Data Center | установлен Tempo Timesheets 4.x |
| Jira PAT | — | Personal Access Token (Профиль → Personal Access Tokens) |

---

## 🚀 Путь 1 — Интерактивный установщик (рекомендуется)

Установщик создаёт venv, записывает `.env`, регистрирует MCP-сервер в VS Code
и опционально проверяет связь с Jira:

```bash
cd jira-tempo-mcp
python install.py
```

Выполняемые шаги:

1. ✅ Проверка Python ≥ 3.11
2. ✅ Создание `.venv` и установка пакета (editable, с dev-зависимостями)
3. ✅ Запись `.env` — запросы Jira URL, имени пользователя, PAT (ввод скрыт через
   `getpass`, права файла `0600`)
4. ✅ Регистрация MCP-сервера в VS Code `mcp.json` — **добавляет** запись в
   существующий файл, не перезаписывает другие серверы. Сначала создаётся
   резервная копия `mcp.json.bak`.
5. ✅ Опциональная проверка связи с Jira (`/rest/api/2/myself`)

> 💡 **Совет:** Запускайте `python install.py` в любой момент, чтобы
> перегенерировать `.env` или перерегистрировать конфигурацию VS Code.
> Установщик идемпотентен.

---

## 🤖 Путь 1b — Non-interactive installation (CI / скрипты / агенты)

Если установщик запускается без TTY (CI, скрипт, агент), используйте флаг
`--non-interactive` (алиасы `--yes`, `-n`) и передавайте параметры через CLI-флаги
или переменные окружения. Интерактивный режим остаётся значением по умолчанию
(без флага работает как раньше).

### Минимальная регистрация (без venv/pip)

Для CI и автоматизации — только пишет `.env.local` и регистрирует MCP-сервер в
`~/.config/Code/User/mcp.json`, пропуская создание venv и `pip install`:

```bash
JIRA_BASE_URL=https://jira.example.com JIRA_USER=user JIRA_PAT=*** \
  python install.py --non-interactive --register-only
```

### Полный non-interactive режим (venv + pip + .env.local + регистрация)

```bash
python install.py --non-interactive \
  --jira-base-url https://jira.example.com \
  --jira-user user \
  --jira-pat "$JIRA_PAT" \
  --jira-timezone Europe/Moscow \
  --log-level INFO
```

### Доступные флаги и переменные

| Флаг | Переменная окружения | По умолчанию | Описание |
| --- | --- | --- | --- |
| `--non-interactive` / `--yes` / `-n` | — | `false` | Пропускает все интерактивные запросы |
| `--register-only` | — | `false` | Пропускает venv/pip, только `.env.local` + регистрация в `mcp.json` |
| `--skip-vscode` | — | `false` | Пропускает регистрацию в VS Code (только `.env.local`) |
| `--jira-base-url` | `JIRA_BASE_URL` | — | Base URL вашего Jira |
| `--jira-user` | `JIRA_USER` | — | Имя пользователя Jira |
| `--jira-pat` | `JIRA_PAT` | — | Personal Access Token (читается также из env, не логируется) |
| `--jira-timezone` | `JIRA_TIMEZONE` | `Europe/Moscow` | IANA timezone |
| `--log-level` | `LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR |

### Поведение при отсутствии обязательных значений

В non-interactive режиме обязательные переменные (`JIRA_BASE_URL`, `JIRA_USER`,
`JIRA_PAT`) разрешаются в следующем порядке: CLI-флаг → переменная окружения →
существующий `~/.config/Code/User/.env.local` → существующий проектный `.env`.

> ⚠️ **Важно:** значения из `.env.example` **не используются** как реальное
> значение — это плейсхолдеры (`your-username`, `your_personal_access_token_here`)
> и они не маскируют отсутствие настоящих данных.

Если ни один источник не предоставляет обязательное значение, установщик
выводит понятную ошибку в stderr с перечнем отсутствующих переменных и
завершается с кодом 1 (не падает с `KeyError`). В этом случае значение из
`.env.example` также не считается «настоящим» — это плейсхолдеры.

```text
Missing required configuration in non-interactive mode.
Non-interactive mode requires the following variables but they are missing
(not set via CLI flag, env var, or existing .env.local):
  • JIRA_PAT
Provide them via flags (--jira-base-url, --jira-user, --jira-pat) or env vars
(JIRA_BASE_URL, JIRA_USER, JIRA_PAT), or run without --non-interactive for
interactive setup.
```

### Пропуск регистрации в VS Code

Если нужен только `.env.local` (например, для Docker-only окружения):

```bash
python install.py --non-interactive --skip-vscode \
  --jira-base-url https://jira.example.com \
  --jira-user user \
  --jira-pat "$JIRA_PAT"
```

### Совместимость с CLI диспетчером

Установщик также доступен через CLI-диспетчер пакета:

```bash
jira-tempo-mcp install --non-interactive --register-only   # эквивалент python install.py
```

---

## 📥 Путь 2 — pip (опубликованный пакет)

> ⚠️ **Пока недоступно.** Пакет **не опубликован в PyPI**, пока GitHub Actions
> отключены, а job `pypi-publish` защищён `if: false` (см.
> [deployment.ru.md](deployment.ru.md)). `pip install jira-tempo-mcp`
> завершится ошибкой 404. Пока публикация в PyPI не включена, используйте
> **интерактивный установщик** (Путь 1), **установку из исходников** (Путь 3)
> или **Docker** (Путь 4).

Команда ниже — целевой сценарий после публикации пакета:

```bash
pip install jira-tempo-mcp
jira-tempo-mcp serve
```

Конфигурация читается из переменных окружения или файла `.env` в рабочей
директории. См. [configuration.ru.md](configuration.ru.md).

---

## 🔧 Путь 3 — из исходников

```bash
git clone https://github.com/Korrnals/jira-tempo-mcp.git
cd jira-tempo-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
jira-tempo-mcp serve
```

> 💡 **Совет:** В Windows PowerShell замените `source .venv/bin/activate` на
> `.venv\Scripts\Activate.ps1`.

---

## 🐳 Путь 4 — Docker

Образ публикуется в GitHub Container Registry при каждом теге `v*`:

```bash
docker run -i --rm \
  --env-file .env \
  ghcr.io/korrnals/jira-tempo-mcp:latest
```

Контейнер запускает `jira-tempo-mcp serve` через stdio. Секреты **никогда**
не вшиваются в образ — передавайте их при запуске через `--env-file` или
Kubernetes Secret. См. [deployment.ru.md](deployment.ru.md).

---

## 🛠️ Создание venv вручную

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Экстра `[dev]` устанавливает `ruff`, `mypy`, `pytest`, `pytest-asyncio`,
`types-pytz` и `pre-commit`.

---

## 🔍 Проверка установки

```bash
# Версия
jira-tempo-mcp --version

# Запуск сервера (stdio)
jira-tempo-mcp serve
```

Если сервер запускается и пишет в stderr `Starting jira-tempo-mcp for
<your-jira-url>`, установка корректна. Сервер работает через stdio — читает
JSON-RPC из stdin и пишет в stdout.

---

## ➡️ Дальнейшие шаги

- ⚙️ [configuration.ru.md](configuration.ru.md) — все переменные окружения
- 🔌 [mcp-integration.ru.md](mcp-integration.ru.md) — подключение сервера к VS Code
- 🖥️ [cli.ru.md](cli.ru.md) — справочник CLI-команд
