# ⚙️ Настройка

Вся конфигурация — через переменные окружения. Сервер читает их при запуске
через `config.py` (валидация pydantic, секреты замаскированы в repr).

---

## ⚙️ Переменные окружения

### 🔌 Подключение к Jira (обязательные)

| Переменная | Обяз. | По умолч. | Описание |
| --- | --- | --- | --- |
| `JIRA_BASE_URL` | да | — | Базовый URL Jira без слэша на конце (напр. `https://jira.example.com`) |
| `JIRA_USER` | да | — | Имя пользователя Jira (логин) — для фильтрации worklog'ов по автору |
| `JIRA_PAT` | да | — | Personal Access Token — **никогда не коммитьте** |

### 🩺 Диагностика отсутствующих обязательных переменных

Если после `load_dotenv()` любая из обязательных переменных (`JIRA_BASE_URL`,
`JIRA_USER`, `JIRA_PAT`) пуста или отсутствует, `load_config()` поднимает
явное исключение `ConfigError` (наследник `ValueError`) с инструкцией для
каждого бэкенда. Сообщение **никогда не содержит значения PAT** — только имя
переменной и описание:

```text
JIRA_PAT (Jira Personal Access Token (PAT)) не найден в окружении.
Проверьте источник (в порядке приоритета):
  • VS Code MCP: укажите envFile в mcp.json → ~/.config/Code/User/.env.local
    (см. docs/mcp-integration.ru.md)
  • CLI: создайте .env в корне репо (cp .env.example .env)
  • Docker: передайте --env-file при запуске
Запустите `python install.py --non-interactive --register-only` для
автоматической настройки.
```

> 💡 **Совет:** `ConfigError` наследует `ValueError`, поэтому существующие
> блоки `except ValueError` и тесты `pytest.raises((RuntimeError, ValueError))`
> продолжают работать. Импортируйте его явно при необходимости:
> `from jira_tempo_mcp.config import ConfigError`.

### 🔌 Подключение к Jira (опциональные)

| Переменная | Обяз. | По умолч. | Описание |
| --- | --- | --- | --- |
| `JIRA_TIMEZONE` | нет | `Europe/Moscow` | Часовой пояс IANA для работы с датами |
| `TEMPO_API_TOKEN` | нет | берётся `JIRA_PAT` | Отдельный токен Tempo API |
| `LOG_LEVEL` | нет | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `JIRA_HTTP_TIMEOUT` | нет | `30.0` | Таймаут HTTP-запросов к Jira/Tempo (секунды) |

### 📝 Еженедельный отчёт (опциональные)

| Переменная | Обяз. | По умолч. | Описание |
| --- | --- | --- | --- |
| `REPORT_OUTPUT_DIR` | нет | `./reports` | Базовая директория для файлов отчётов |
| `REPORT_AUTHOR_NAME` | нет | `JIRA_USER` | Имя автора в заголовке отчёта |
| `REPORT_SECTION_MAP` | нет | пусто | JSON-словарь: ключ задачи → заголовок секции |
| `REPORT_SECTION_MAP_FILE` | нет | пусто | Путь к JSON-файлу с маппингом секций |
| `REPORT_FILENAME_PREFIX` | нет | `JIRA_USER` | Префикс имён файлов отчётов |
| `REPORT_STABLE_ORDER` | нет | пусто | JSON-список ключей задач в стабильном порядке |
| `REPORT_NON_ISSUE_SECTIONS` | нет | пусто | JSON-список заголовков секций без ключей задач |

Подробнее о переменных отчёта — в [reports.ru.md](reports.ru.md).

### 👥 Rate-limiting командного отчёта (опциональные)

| Переменная | Обяз. | По умолч. | Описание |
| --- | --- | --- | --- |
| `TEMPO_MAX_CONCURRENT_REQUESTS` | нет | `3` | Максимум параллельных запросов к Tempo в командном отчёте |
| `TEMPO_REQUEST_DELAY_MS` | нет | `100` | Задержка (мс) между пакетами запросов |
| `TEMPO_MAX_RETRIES` | нет | `3` | Число повторов при HTTP 429 (экспоненциальная задержка) |
| `REPORT_TEAM_OUTPUT_DIR` | нет | пусто | Директория для командных отчётов (пусто = `REPORT_OUTPUT_DIR`) |

### 🎨 Кастомные шаблоны отчётов (опциональные)

| Переменная | Обяз. | По умолч. | Описание |
| --- | --- | --- | --- |
| `REPORT_TEMPLATE` | нет | `default` | Имя шаблона для `generate_weekly_report` |
| `REPORT_TEMPLATE_PATH` | нет | пусто | Явный путь к файлу шаблона (переопределяет `REPORT_TEMPLATE`) |
| `REPORT_TEMPLATE_DIR` | нет | `~/.config/jira-tempo-mcp/templates/` | Директория для кастомных шаблонов |
| `REPORT_TEMPLATE_ALLOW_PY` | нет | `false` | Opt-in для загрузки `.py`-шаблонов (риск выполнения кода) |

Подробнее о кастомных шаблонах — в
[reports.ru.md#кастомные-шаблоны](reports.ru.md#кастомные-шаблоны).

---

## 🔑 `.env` для CLI

Сервер автоматически загружает `.env` из корня проекта (через
`python-dotenv`). Скопируйте шаблон и заполните PAT:

```bash
cp .env.example .env
# Отредактируйте .env — укажите JIRA_PAT
chmod 0600 .env
```

Пример `.env`:

```bash
JIRA_BASE_URL=https://jira.example.com
JIRA_USER=your-username
JIRA_PAT=your_personal_access_token_here
JIRA_TIMEZONE=Europe/Moscow
LOG_LEVEL=INFO
```

> 🔒 `.env` добавлен в `.gitignore`. Установщик создаёт его с правами `0600`.

---

## 🔑 `.env.local` для VS Code MCP

VS Code MCP-host читает секреты из единого `envFile`, указанного в
`mcp.json`. Рекомендуемый паттерн — один `.env.local` на пользователя, в
котором хранятся секреты всех MCP-серверов:

```bash
# ~/.config/Code/User/.env.local
JIRA_PAT=your_personal_access_token_here
TEMPO_API_TOKEN=your_tempo_token_here
```

Затем в `mcp.json` укажите **абсолютный путь** (см.
[mcp-integration.ru.md](mcp-integration.ru.md) — почему `~` не работает в
sandbox-окружениях):

```json
{
  "servers": {
    "jira-tempo": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "jira_tempo_mcp.server"],
      "envFile": "/home/your-username/.config/Code/User/.env.local",
      "env": {
        "JIRA_BASE_URL": "https://jira.example.com",
        "JIRA_USER": "your-username",
        "PYTHONPATH": "/path/to/jira-tempo-mcp/src"
      }
    }
  }
}
```

`JIRA_PAT` подставляется из `.env.local`; не-секретные переменные живут в `env`.

---

## 📋 Примеры конфигурации

### Минимальная (Jira PAT используется и для Tempo)

```bash
JIRA_BASE_URL=https://jira.example.com
JIRA_USER=your-username
JIRA_PAT=your_personal_access_token_here
```

### Отдельный токен Tempo

```bash
JIRA_BASE_URL=https://jira.example.com
JIRA_USER=your-username
JIRA_PAT=your_jira_pat
TEMPO_API_TOKEN=your_tempo_api_token
```

### Кастомные секции отчёта

```bash
REPORT_SECTION_MAP='{"PROJECT-100":"Разработка","PROJECT-101":"Ревью кода"}'
REPORT_STABLE_ORDER='["PROJECT-100", "PROJECT-101"]'
REPORT_NON_ISSUE_SECTIONS='["Совещания команды", "Jira triage"]'
REPORT_FILENAME_PREFIX=your-username
```

---

## 🔒 Обработка секретов

- `JIRA_PAT` и `TEMPO_API_TOKEN` замаскированы как `***` в `Config.__repr__`
  — случайный `print(config)` не утечёт.
- URL с встроенными учётными данными очищаются через `_redact()` перед логированием.
- Тела ошибок API обрезаются до 200 символов для снижения шума и возможной
  утечки токена.

Полная модель безопасности — в [architecture.ru.md](architecture.ru.md#безопасность).

---

## ➡️ Дальнейшие шаги

- 🔌 [mcp-integration.ru.md](mcp-integration.ru.md) — подключение сервера к VS Code
- 📝 [reports.ru.md](reports.ru.md) — настройка еженедельного отчёта
- 🐛 [troubleshooting.ru.md](troubleshooting.ru.md) — ошибки конфигурации
