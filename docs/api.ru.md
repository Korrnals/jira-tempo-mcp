# API — MCP-инструменты

Сервер открывает 9 инструментов через Model Context Protocol. Каждый
инструмент определён в `src/jira_tempo_mcp/server.py` и диспетчеризуется
через таблицу (`_TOOL_HANDLERS`).

## Индекс инструментов

| Инструмент | Назначение |
| --- | --- |
| [`list_worklogs`](#list_worklogs) | Список worklog'ов Tempo за период или один день |
| [`get_worklog`](#get_worklog) | Получить один worklog по Tempo ID |
| [`create_worklog`](#create_worklog) | Учесть время на задаче Jira |
| [`delete_worklog`](#delete_worklog) | Удалить worklog по ID |
| [`get_issue`](#get_issue) | Получить метаданные задачи Jira |
| [`list_favorite_issues`](#list_favorite_issues) | Список избранных задач текущего пользователя |
| [`generate_weekly_report`](#generate_weekly_report) | Сгенерировать еженедельный отчёт `.txt` |
| [`generate_team_report`](#generate_team_report) | Сгенерировать командный отчёт для нескольких пользователей |
| [`list_report_templates`](#list_report_templates) | Показать доступные шаблоны отчётов |

---

## `list_worklogs`

Список worklog'ов Tempo за период (или один день). Возвращается только
фактически учтённое время — плановое исключается.

**Параметры:**

| Имя | Тип | Обяз. | Описание |
| --- | --- | --- | --- |
| `date_from` | string | нет | Начальная дата (ISO `YYYY-MM-DD`). По умолч. сегодня. |
| `date_to` | string | нет | Конечная дата (ISO `YYYY-MM-DD`). По умолч. `date_from`. |

**Пример вызова:**

```json
{
  "name": "list_worklogs",
  "arguments": {
    "date_from": "2026-06-16",
    "date_to": "2026-06-20"
  }
}
```

**Возвращает:** по одной строке на worklog:

```text
Worklogs 2026-06-16 .. 2026-06-20 (5 entries):
- 2026-06-16 | PROJECT-100 | 1h 30m | id=12345 | Implemented login flow
- 2026-06-17 | PROJECT-101 | 2h | id=12346 | Code review
```

---

## `get_worklog`

Получить один worklog Tempo по его внутреннему ID.

**Параметры:**

| Имя | Тип | Обяз. | Описание |
| --- | --- | --- | --- |
| `worklog_id` | string | да | ID worklog'а Tempo |

**Пример вызова:**

```json
{
  "name": "get_worklog",
  "arguments": { "worklog_id": "12345" }
}
```

**Возвращает:** строки ключ/значение со всеми полями worklog'а:

```text
Worklog 12345:
  tempoWorklogId: 12345
  issueKey: PROJECT-100
  timeSpentSeconds: 5400
  startDate: 2026-06-16
  comment: Implemented login flow
```

---

## `create_worklog`

Учесть время на задаче Jira через Tempo. Worklog приписывается владельцу
токена, если не задан `author_account_id`.

**Параметры:**

| Имя | Тип | Обяз. | Описание |
| --- | --- | --- | --- |
| `issue_key` | string | да | Ключ задачи Jira (напр. `PROJECT-100`) |
| `time_spent` | string | да | Длительность: `1h 30m`, `2h`, `45m`, `1d 2h` |
| `comment` | string | нет | Опциональный комментарий к worklog'у |
| `date_started` | string | нет | ISO 8601 datetime со смещением. По умолч. сейчас. |
| `author_account_id` | string | нет | Опциональный Tempo worker key. По умолч. владелец токена. |

**Единицы длительности:** `w` (неделя = 5d), `d` (день = 8h), `h` (час), `m` (минута).

**Пример вызова:**

```json
{
  "name": "create_worklog",
  "arguments": {
    "issue_key": "PROJECT-100",
    "time_spent": "1h 30m",
    "comment": "Implemented login flow",
    "date_started": "2026-06-19T10:00:00+03:00"
  }
}
```

**Возвращает:**

```text
Tracked 1h 30m on PROJECT-100 at 2026-06-19T10:00:00+03:00. Worklog ID: 12345. Comment: Implemented login flow
```

---

## `delete_worklog`

Удалить worklog Tempo по его ID. Используется для отмены/исправления
неправильно учтённого времени.

**Параметры:**

| Имя | Тип | Обяз. | Описание |
| --- | --- | --- | --- |
| `worklog_id` | string | да | ID worklog'а Tempo для удаления |

**Пример вызова:**

```json
{
  "name": "delete_worklog",
  "arguments": { "worklog_id": "12345" }
}
```

**Возвращает:**

```text
Deleted worklog 12345.
```

---

## `get_issue`

Получить метаданные задачи Jira: summary, статус, проект.

**Параметры:**

| Имя | Тип | Обяз. | Описание |
| --- | --- | --- | --- |
| `issue_key` | string | да | Ключ задачи Jira (напр. `PROJECT-100`) |

**Пример вызова:**

```json
{
  "name": "get_issue",
  "arguments": { "issue_key": "PROJECT-100" }
}
```

**Возвращает:**

```text
PROJECT-100: Implement login flow
Status: In Progress
Project: Web Platform
```

---

## `list_favorite_issues`

Список избранных задач текущего пользователя Jira. Возвращает ключи и summary.

**Параметры:** нет.

**Пример вызова:**

```json
{
  "name": "list_favorite_issues",
  "arguments": {}
}
```

**Возвращает:**

```text
Favorite issues (3):
- PROJECT-100: Implement login flow
- PROJECT-101: Code review process
- PROJECT-102: Fix CI pipeline
```

---

## `generate_weekly_report`

Сгенерировать еженедельный отчёт из worklog'ов Tempo и сохранить его как
файл `.txt`. Группирует worklog'и по задачам, отображает известные задачи в
стабильные секции и записывает `<prefix>_<DDMMYY>-<DDMMYY>.txt` в
настроенную директорию.

**Параметры:**

| Имя | Тип | Обяз. | Описание |
| --- | --- | --- | --- |
| `target_date` | string | нет | Любая дата целевой недели (ISO `YYYY-MM-DD`). По умолч. сегодня. |
| `output_dir` | string | нет | Директория вывода. По умолч. `REPORT_OUTPUT_DIR` или `./reports`. Должна быть внутри разрешённого корня. |

**Пример вызова:**

```json
{
  "name": "generate_weekly_report",
  "arguments": { "target_date": "2026-06-19" }
}
```

**Возвращает:**

```text
Weekly report generated: /path/to/reports/your-username_160620-200620.txt
```

Настройка отчёта (маппинг секций, стабильный порядок, не-задачные секции) —
в [reports.ru.md](reports.ru.md).

---

## `generate_team_report`

Сгенерировать командный отчёт из worklog'ов Tempo для нескольких
пользователей Jira. Для каждого пользователя загружаются worklog'ы с
ограничением параллельности (защита от rate-limit), рендерятся секции по
пользователям и агрегированная сводка, файл `team_<DDMMYY>-<DDMMYY>.txt`
записывается в настроенную директорию.

**Параметры:**

| Имя | Тип | Обязательный | Описание |
| --- | --- | --- | --- |
| `users` | array<string> | да | Имена пользователей Jira (непустой список) |
| `date_from` | string | нет | Начальная дата (ISO `YYYY-MM-DD`). По умолчанию понедельник текущей недели. |
| `date_to` | string | нет | Конечная дата (ISO `YYYY-MM-DD`). По умолчанию пятница текущей недели. |
| `section_map` | object | нет | Опциональная замена для `REPORT_SECTION_MAP` (ключ задачи → заголовок секции) |
| `template` | string | нет | Имя шаблона. По умолчанию `team_report`. |
| `output_dir` | string | нет | Директория вывода. По умолчанию `REPORT_TEAM_OUTPUT_DIR` или `REPORT_OUTPUT_DIR`. Должна быть внутри разрешённого корня. |

**Rate-limiting:** параллельные запросы к Tempo ограничены
`TEMPO_MAX_CONCURRENT_REQUESTS` (по умолчанию 3). Между пакетами запросов
вставляется задержка `TEMPO_REQUEST_DELAY_MS` (по умолчанию 100 мс).
При HTTP 429 клиент повторяет запрос с экспоненциальной задержкой до
`TEMPO_MAX_RETRIES` (по умолчанию 3) раз.

**Пример вызова:**

```json
{
  "name": "generate_team_report",
  "arguments": {
    "users": ["alice", "bob", "carol"],
    "date_from": "2026-06-15",
    "date_to": "2026-06-19"
  }
}
```

**Возвращает:**

```text
Team report written: /path/to/reports/team_150626-190626.txt
Grand total: 24h across 3 users.
Per-user totals:
  - alice: 10h
  - bob: 8h
  - carol: 6h
Top issues:
  - PROJECT-100 (Implement login flow): 12h
```

---

## `list_report_templates`

Показать доступные шаблоны отчётов (встроенные + кастомные). Возвращает
имя и описание каждого шаблона. Кастомные шаблоны обнаруживаются в
`REPORT_TEMPLATE_DIR`.

**Параметры:** нет.

**Пример вызова:**

```json
{
  "name": "list_report_templates",
  "arguments": {}
}
```

**Возвращает:**

```text
Report templates (4):
- default: Weekly report grouped by issue with stable sections...
- team_report: Team report: per-user sections with issue breakdown...
- weekly_summary: Compact weekly summary: total hours, top 5 issues...
- custom: My custom Jinja2 template
```

См. [reports.md#custom-templates](reports.md#custom-templates) — как
добавлять кастомные шаблоны.

---

## Обработка ошибок

Все инструменты при сбое возвращают пользовательскую строку ошибки (не
сырой trace исключения). Частые шаблоны ошибок:

| Ошибка | Причина |
| --- | --- |
| `Invalid issue key '...'` | ключ не соответствует `^[A-Z][A-Z0-9]+-\d+$` |
| `Invalid date for ...` | дата не в ISO `YYYY-MM-DD` |
| `Could not parse duration: '...'` | в `time_spent` нет валидных токенов `w/d/h/m` |
| `Jira/Tempo API error: 401 ...` | невалидный или истёкший PAT |
| `output_dir '...' resolves outside the allowed root` | попытка path traversal |
| `Could not identify your Tempo worker key` | несоответствие `JIRA_USER` или связь с Tempo |

## Дальнейшие шаги

- [reports.ru.md](reports.ru.md) — настройка еженедельного отчёта
- [configuration.ru.md](configuration.ru.md) — переменные окружения, влияющие на инструменты
- [architecture.ru.md](architecture.ru.md) — как диспетчеризуются инструменты
