# Еженедельные отчёты

Инструмент `generate_weekly_report` создаёт `.txt` еженедельный отчёт из
worklog'ов Tempo.

## Как это работает

1. Выбираются все worklog'и Tempo за целевую неделю (пн–пт).
2. Worklog'и группируются по ключу задачи.
3. Известные задачи отображаются в стабильные секции отчёта (через `REPORT_SECTION_MAP`).
4. Для неизвестных задач подтягиваются summary из Jira.
5. Записывается `<prefix>_<DDMMYY>-<DDMMYY>.txt` в настроенную директорию.

## Формат имени файла

```text
<prefix>_<DDMMYY>-<DDMMYY>.txt
```

- `<prefix>` — `REPORT_FILENAME_PREFIX` (по умолч. `JIRA_USER`)
- `<DDMMYY>-<DDMMYY>` — даты понедельника и пятницы целевой недели

Пример: `your-username_160620-200620.txt`

## Маппинг секций

Отобразите ключи задач в заголовки секций отчёта через переменные окружения:

```bash
# Вариант 1: инлайн JSON
export REPORT_SECTION_MAP='{"PROJECT-100":"Разработка","PROJECT-101":"Ревью кода"}'

# Вариант 2: JSON-файл
export REPORT_SECTION_MAP_FILE=/path/to/sections.json
```

Формат `sections.json`:

```json
{
  "PROJECT-100": "Разработка",
  "PROJECT-101": "Ревью кода",
  "PROJECT-102": "Инфраструктура"
}
```

Задачи, отсутствующие в маппинге, группируются под своим summary из Jira.

## Стабильный порядок

Зафиксируйте порядок конкретных ключей задач (если по ним есть worklog'и):

```bash
export REPORT_STABLE_ORDER='["PROJECT-100", "PROJECT-101", "PROJECT-102"]'
```

Задачи из `REPORT_STABLE_ORDER` идут первыми в указанном порядке. Остальные
— в порядке появления.

## Не-задачные секции

Добавьте заголовки секций без ключа задачи (совещания, административная
работа):

```bash
export REPORT_NON_ISSUE_SECTIONS='["Совещания команды", "Jira triage"]'
```

Эти секции появляются в отчёте только с заголовком — без префикса ключа
задачи. Это плейсхолдеры для работы, не привязанной к конкретной задаче
Jira.

## Остальные переменные отчёта

| Переменная | По умолч. | Эффект |
| --- | --- | --- |
| `REPORT_OUTPUT_DIR` | `./reports` | Базовая директория для файлов отчётов |
| `REPORT_AUTHOR_NAME` | `JIRA_USER` | Имя автора в заголовке отчёта |
| `REPORT_FILENAME_PREFIX` | `JIRA_USER` | Префикс имён файлов отчётов |

## Пример отчёта

```text
Weekly report: 16.06.2026 – 20.06.2026
Author: your-username

Разработка
- PROJECT-100: Implement login flow — 3h 30m
- PROJECT-100: Fix login redirect bug — 1h

Ревью кода
- PROJECT-101: Review PR #42 — 2h

Инфраструктура
- PROJECT-102: Rotate CI secrets — 1h 15m

Совещания команды
- (без ключа задачи)

Jira triage
- (без ключа задачи)
```

## Защита от path traversal

Параметр `output_dir` инструмента `generate_weekly_report` проверяется на
path traversal. Разрешённый путь должен быть внутри разрешённого корня
(`REPORT_OUTPUT_DIR` или `./reports`). Пути вида `../../etc` отклоняются
с явной ошибкой.

## Дальнейшие шаги

- [api.ru.md#generate_weekly_report](api.ru.md#generate_weekly_report) — параметры инструмента
- [configuration.ru.md](configuration.ru.md#еженедельный-отчёт-опциональные) — все переменные отчёта
- [troubleshooting.ru.md](troubleshooting.ru.md) — ошибки, связанные с отчётом
