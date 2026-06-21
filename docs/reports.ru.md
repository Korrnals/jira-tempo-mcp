# 📝 Еженедельные отчёты

Инструмент `generate_weekly_report` создаёт `.txt` еженедельный отчёт из
worklog'ов Tempo.

---

## 📝 Как это работает

1. Выбираются все worklog'и Tempo за целевую неделю (пн–пт).
2. Worklog'и группируются по ключу задачи.
3. Известные задачи отображаются в стабильные секции отчёта (через `REPORT_SECTION_MAP`).
4. Для неизвестных задач подтягиваются summary из Jira.
5. Записывается `<prefix>_<DDMMYY>-<DDMMYY>.txt` в настроенную директорию.

---

## 📄 Формат имени файла

```text
<prefix>_<DDMMYY>-<DDMMYY>.txt
```

- `<prefix>` — `REPORT_FILENAME_PREFIX` (по умолч. `JIRA_USER`)
- `<DDMMYY>-<DDMMYY>` — даты понедельника и пятницы целевой недели

> 💡 **Совет:** Пример: `your-username_160620-200620.txt`

---

## 🗺️ Маппинг секций

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

> 💡 **Совет:** Задачи, отсутствующие в маппинге, группируются под своим summary из Jira.

---

## 📊 Стабильный порядок

Зафиксируйте порядок конкретных ключей задач (если по ним есть worklog'и):

```bash
export REPORT_STABLE_ORDER='["PROJECT-100", "PROJECT-101", "PROJECT-102"]'
```

Задачи из `REPORT_STABLE_ORDER` идут первыми в указанном порядке. Остальные
— в порядке появления.

---

## 📋 Не-задачные секции

Добавьте заголовки секций без ключа задачи (совещания, административная
работа):

```bash
export REPORT_NON_ISSUE_SECTIONS='["Совещания команды", "Jira triage"]'
```

Эти секции появляются в отчёте только с заголовком — без префикса ключа
задачи. Это плейсхолдеры для работы, не привязанной к конкретной задаче
Jira.

---

## ⚙️ Остальные переменные отчёта

| Переменная | По умолч. | Эффект |
| --- | --- | --- |
| `REPORT_OUTPUT_DIR` | `./reports` | Базовая директория для файлов отчётов |
| `REPORT_AUTHOR_NAME` | `JIRA_USER` | Имя автора в заголовке отчёта |
| `REPORT_FILENAME_PREFIX` | `JIRA_USER` | Префикс имён файлов отчётов |

---

## 📝 Пример отчёта

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

---

## 👥 Командные отчёты

Инструмент `generate_team_report` создаёт `.txt` командный отчёт из
worklog'ов Tempo для нескольких пользователей Jira. Каждый пользователь
получает секцию с разбивкой по задачам; агрегированная сводка показывает
итоги по каждому пользователю, общий итог и топ-5 задач команды.

### 📄 Формат имени файла

```text
team_<DDMMYY>-<DDMMYY>.txt
```

> 💡 **Совет:** Пример: `team_150626-190626.txt`

### 🛡️ Rate-limiting

Командный отчёт делает один запрос к Tempo на каждого пользователя. Чтобы
не упереться в rate limit Tempo, параллельность ограничена семафором:

| Переменная | По умолчанию | Действие |
| --- | --- | --- |
| `TEMPO_MAX_CONCURRENT_REQUESTS` | `3` | Максимум параллельных запросов к Tempo |
| `TEMPO_REQUEST_DELAY_MS` | `100` | Задержка (мс) между пакетами запросов |
| `TEMPO_MAX_RETRIES` | `3` | Число повторов при HTTP 429 (экспоненциальная задержка: 1с, 2с, 4с) |
| `REPORT_TEAM_OUTPUT_DIR` | пусто | Директория для командных отчётов (пусто = `REPORT_OUTPUT_DIR`) |

> 💡 **Совет:** Пользователи без worklog'ов перечислены в сводке под «Без отработанного времени».

### 📝 Пример командного отчёта

```text
Командный отчёт за неделю (15.06.2026 - 19.06.2026):

== alice (10h) ==
  - PROJECT-100 (Section A):
      + Stand support
  - PROJECT-200 (Task B):
      + 2h отработано

== bob (8h) ==
  - PROJECT-100 (Section A):
      + Review PR

== Сводка по команде ==
Всего отработано: 18h

По сотрудникам:
  - alice: 10h
  - bob: 8h

Топ-5 задач команды:
  - PROJECT-100 (Section A): 12h
  - PROJECT-200 (Task B): 6h
```

---

## 🎨 Кастомные шаблоны

Начиная с v0.2.0 рендеринг отчётов делегируется шаблонам. Встроенные
шаблоны:

| Шаблон | Описание |
| --- | --- |
| `default` | Еженедельный отчёт по задачам со стабильными секциями (исходный формат) |
| `weekly_summary` | Краткая сводка: всего часов, топ-5 задач, без детализации |
| `team_report` | Командный отчёт: секции по пользователям + агрегированная сводка |

### 📌 Выбор шаблона

Передайте параметр `template` в `generate_weekly_report` или
`generate_team_report`, либо установите переменную `REPORT_TEMPLATE`.

### ➕ Добавление кастомных шаблонов

Поместите файлы шаблонов в `REPORT_TEMPLATE_DIR` (по умолчанию
`~/.config/jira-tempo-mcp/templates/`). Поддерживаются два формата:

#### 📜 Jinja2-шаблоны (`.j2`) — безопасны по умолчанию

Загружаются в `SandboxedEnvironment`. Контекст шаблона включает:
`worklogs`, `config`, `format_seconds`, `format_date`, `users`,
`per_user_worklogs`, `issue_titles`, `monday`, `friday`.

Пример `simple.j2`:

```jinja
Всего worklog'ов: {{ worklogs | length }}
Итого: {{ format_seconds(worklogs | map(attribute='timeSpentSeconds') | sum) }}
```

> ✅ Небезопасные конструкции (например `{{ config.__class__ }}`) блокируются
> песочницей.

#### 🐍 Python-шаблоны (`.py`) — opt-in, риск выполнения кода

Загружаются только при `REPORT_TEMPLATE_ALLOW_PY=1`. Модуль должен
предоставлять атрибут `TEMPLATE`, реализующий протокол `ReportTemplate`:

```python
class MyTemplate:
    name = "my_template"
    description = "Мой кастомный шаблон"

    def render(self, worklogs, config, **kwargs):
        return f"Получено {len(worklogs)} worklog'ов"

TEMPLATE = MyTemplate()
```

> ⚠️ **Внимание:** Python-шаблоны выполняют произвольный код. Загружайте
> `.py`-файлы только из доверенного источника. При каждой загрузке
> пишется предупреждение в лог.

### 📋 Список доступных шаблонов

Используйте инструмент `list_report_templates` чтобы увидеть все
встроенные и кастомные шаблоны.

---

## 🛡️ Защита от path traversal

Параметр `output_dir` инструмента `generate_weekly_report` проверяется на
path traversal. Разрешённый путь должен быть внутри разрешённого корня
(`REPORT_OUTPUT_DIR` или `./reports`). Пути вида `../../etc` отклоняются
с явной ошибкой.

---

## ➡️ Дальнейшие шаги

- 🌐 [api.ru.md#generate_weekly_report](api.ru.md#generate_weekly_report) — параметры инструмента
- ⚙️ [configuration.ru.md](configuration.ru.md#еженедельный-отчёт-опциональные) — все переменные отчёта
- 🐛 [troubleshooting.ru.md](troubleshooting.ru.md) — ошибки, связанные с отчётом
