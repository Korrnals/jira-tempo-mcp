# Установка

Способы установки `jira-tempo-mcp` — четыре пути: интерактивный установщик,
pip, из исходников, Docker.

## Требования

| Требование | Версия | Примечания |
| --- | --- | --- |
| Python | 3.11+ | рекомендуется 3.12 |
| pip | последняя | входит в комплект Python |
| Jira | Server / Data Center | установлен Tempo Timesheets 4.x |
| Jira PAT | — | Personal Access Token (Профиль → Personal Access Tokens) |

## Путь 1 — Интерактивный установщик (рекомендуется)

Установщик создаёт venv, записывает `.env`, регистрирует MCP-сервер в VS Code
и опционально проверяет связь с Jira:

```bash
cd jira-tempo-mcp
python install.py
```

Выполняемые шаги:

1. Проверка Python ≥ 3.11
2. Создание `.venv` и установка пакета (editable, с dev-зависимостями)
3. Запись `.env` — запросы Jira URL, имени пользователя, PAT (ввод скрыт через
   `getpass`, права файла `0600`)
4. Регистрация MCP-сервера в VS Code `mcp.json` — **добавляет** запись в
   существующий файл, не перезаписывает другие серверы. Сначала создаётся
   резервная копия `mcp.json.bak`.
5. Опциональная проверка связи с Jira (`/rest/api/2/myself`)

Запускайте `python install.py` в любой момент, чтобы перегенерировать `.env`
или перерегистрировать конфигурацию VS Code.

## Путь 2 — pip (опубликованный пакет)

```bash
pip install jira-tempo-mcp
jira-tempo-mcp serve
```

Конфигурация читается из переменных окружения или файла `.env` в рабочей
директории. См. [configuration.ru.md](configuration.ru.md).

## Путь 3 — из исходников

```bash
git clone https://github.com/Korrnals/jira-tempo-mcp.git
cd jira-tempo-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
jira-tempo-mcp serve
```

В Windows PowerShell замените `source .venv/bin/activate` на
`.venv\Scripts\Activate.ps1`.

## Путь 4 — Docker

Образ публикуется в GitHub Container Registry при каждом теге `v*`:

```bash
docker run -i --rm \
  --env-file .env \
  ghcr.io/korrnals/jira-tempo-mcp:latest
```

Контейнер запускает `jira-tempo-mcp serve` через stdio. Секреты **никогда**
не вшиваются в образ — передавайте их при запуске через `--env-file` или
Kubernetes Secret. См. [deployment.ru.md](deployment.ru.md).

## Создание venv вручную

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Экстра `[dev]` устанавливает `ruff`, `mypy`, `pytest`, `pytest-asyncio`,
`types-pytz` и `pre-commit`.

## Проверка установки

```bash
# Версия
jira-tempo-mcp --version

# Запуск сервера (stdio)
jira-tempo-mcp serve
```

Если сервер запускается и пишет в stderr `Starting jira-tempo-mcp for
<your-jira-url>`, установка корректна. Сервер работает через stdio — читает
JSON-RPC из stdin и пишет в stdout.

## Дальнейшие шаги

- [configuration.ru.md](configuration.ru.md) — все переменные окружения
- [mcp-integration.ru.md](mcp-integration.ru.md) — подключение сервера к VS Code
- [cli.ru.md](cli.ru.md) — справочник CLI-команд
