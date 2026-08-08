# 🎨 Шаблоны отчётов — справочник

Как писать, регистрировать и выбирать собственные шаблоны отчётов для
`jira-tempo-mcp`. Это **справочник для авторов** — для людей и агентов,
которые делают свои шаблоны. Короткий обзор и список встроенных шаблонов —
в [reports.ru.md](reports.ru.md#-пользовательские-шаблоны).

Шаблон превращает список worklog-ов Tempo в строку отчёта. Отрисовка
**подключаемая с v0.2.0**: положите файл в директорию — и он становится
доступен по имени. Без правки кода и без перезапуска сервера (достаточно
перезагрузить конфигурацию MCP-сервера).

---

## 🧩 Два движка

| Движок | Расширение | Безопасен по умолчанию? | Когда использовать |
| --- | --- | --- | --- |
| **Jinja2** | `.j2` | ✅ Да — работает в `SandboxedEnvironment` | Вёрстка текста, циклы, форматирование (рекомендуется почти всегда) |
| **Python** | `.py` | ⚠️ Нет — выполняет произвольный код, **только по явному включению** | Логика, слишком сложная для шаблона: внешние библиотеки, тяжёлая агрегация, побочные эффекты |

Jinja2 — рекомендуемый путь. Шаблон `.py` используйте только тогда, когда
нужен полноценный Python — и только для доверенных файлов.

---

## 📁 Где живут шаблоны

Свои шаблоны обнаруживаются в **директории шаблонов**:

| ОС | Путь по умолчанию |
| --- | --- |
| **Linux** | `~/.config/jira-tempo-mcp/templates/` |
| **macOS** | `~/Library/Application Support/jira-tempo-mcp/templates/` |
| **Windows** | `%APPDATA%\jira-tempo-mcp\templates\` |

> По умолчанию путь строится от `Path.home()`, поэтому на любой ОС это
> `~/.config/jira-tempo-mcp/templates/`. Переопределите переменной
> `REPORT_TEMPLATE_DIR`.

При генерации отчёта директория сканируется:

- `.j2` → загружается в песочницу Jinja2. **Имя шаблона — это имя файла без расширения** (`standup.j2` → имя `standup`).
- `.py` → загружается только при `REPORT_TEMPLATE_ALLOW_PY=1` (см. [§Шаблоны Python](#-шаблоны-python-py)).
- Файлы, начинающиеся с `_`, и поддиректории игнорируются.
- Файлы с другими расширениями игнорируются.

### Обнаружение и разрешение

Загрузчик (`src/jira_tempo_mcp/templates/loader.py`) строит реестр
**встроенных + своих** шаблонов. Приоритет при генерации отчёта:

1. `REPORT_TEMPLATE_PATH` — явный путь к файлу шаблона (загружается отдельно, высший приоритет).
2. `REPORT_TEMPLATE` (или параметр `template` инструмента) — **имя**, которое ищется в реестре.
3. Фолбэк на встроенный шаблон **`default`**, если ничего не подошло.

```
REPORT_TEMPLATE_PATH  →  REPORT_TEMPLATE / параметр template  →  "default"
```

---

## 📜 Шаблоны Jinja2 (`.j2`)

Файл `.j2` — это простой текст с синтаксисом Jinja2 (`{{ ... }}` для вывода,
`{% ... %}` для управляющих конструкций). Загружается в
[`SandboxedEnvironment`](https://jinja.palletsprojects.com/en/stable/sandbox/)
со следующими настройками:

| Настройка | Значение | Эффект |
| --- | --- | --- |
| `autoescape` | `False` | Вывод — простой текст, не HTML; никакого экранирования сущностей |
| `trim_blocks` | `True` | Блочный тег на отдельной строке не оставляет пустую строку |
| `lstrip_blocks` | `True` | Пробелы перед блочным тегом отсекаются |

Поскольку `autoescape=False`, что написали — то и получили. А
`trim_blocks`/`lstrip_blocks` убирают лишние пустые строки в готовом отчёте.

### 🧠 Контекст Jinja2

При отрисовке доступны следующие переменные. Гарантированы только они; всё
остальное приходит из внутренних kwargs и **не** входит в стабильный контракт.

| Переменная | Тип | Описание |
| --- | --- | --- |
| `worklogs` | `list[dict]` | Worklog-и Tempo за неделю (см. [§Поля worklog](#-поля-worklog)). Пустой список, если время не учтено. |
| `config` | `Config` | Объект [`Config`](configuration.ru.md) времени выполнения. Читайте поля вроде `config.jira_user`, `config.report_author_header`. |
| `monday` | `date \| None` | Понедельник целевой недели (`datetime.date`). |
| `friday` | `date \| None` | Пятница целевой недели. |
| `users` | `list` | Упорядоченный список пользователей — кортежи `(username, display_name)` для командных отчётов; пуст для отчёта по одному пользователю. |
| `per_user_worklogs` | `dict[str, list[dict]]` | Соответствие `username → worklog-и` (командные отчёты). Пусто для одиночного отчёта. |
| `issue_titles` | `dict[str, str]` | `issue_key → человекочитаемое summary` (например `{"PROJ-123": "Починить логин"}`). |
| `summary` | `str` | Короткая сводная строка (командные отчёты). Может быть пустой. |
| `format_seconds(seconds)` | callable | Человекочитаемая длительность, например `format_seconds(5400)` → `"1ч 30м"`. |
| `format_date(d)` | callable | Дата в формате `DD.MM.YYYY`, например `format_date(monday)` → `"08.06.2026"`. |

> **Важно:** как вызываемые объекты внедряются только `format_seconds` и
> `format_date`. Разделяемые хелперы `format_date_short`, `week_range`,
> `extract_issue_key`, `extract_seconds` **не** доступны внутри `.j2` —
> используйте фильтры Jinja2 или шаблоны Python, если они нужны.

Любые дополнительные kwargs от движка тоже доступны, но это детали
реализации и могут меняться между версиями. Для переносимых шаблонов
держитесь таблицы выше.

### 📦 Поля worklog

`worklogs` — список сырых объектов worklog Tempo Timesheets 4. Поля, на
которые опираются встроенные шаблоны:

| Поле | Тип | Примечания |
| --- | --- | --- |
| `timeSpentSeconds` | `int` | Время в секундах. Главный ключ агрегации. |
| `issueKey` | `str` | Ключ задачи Jira, например `"PROJ-123"`. Фолбэк — `issue["key"]`. |
| `started` | `str` | Когда отработано, например `"2026-06-08 00:00:00.000"`. Принимается фолбэк `startDate`. |
| `comment` | `str \| dict` | Комментарий к worklog. `dict` с ключом `content` тоже обрабатывается. |
| `authorAccountId` | `str` | Идентификатор аккаунта исполнителя. Фолбэки: `workerKey`, затем `author["key"]` / `author["accountId"]`. |

Словарь — немодифицированный ответ Tempo, поэтому **могут присутствовать и
другие поля** (`id`, `description`, `updated` и т. п.). Встроенные шаблоны на
них не опираются — используйте на своё усмотрение.

### 🔧 Доступные фильтры Jinja2

Песочница несёт стандартный набор фильтров Jinja2. Самые полезные для отчётов:

| Фильтр | Пример | Результат |
| --- | --- | --- |
| `length` | `{{ worklogs \| length }}` | Количество worklog-ов |
| `sum` | `{{ worklogs \| map(attribute='timeSpentSeconds') \| sum }}` | Сумма секунд |
| `groupby` | `{% for key, items in worklogs \| groupby('issueKey') %}` | Группировка по полю |
| `sort` | `{% for wl in worklogs \| sort(attribute='timeSpentSeconds', reverse=true) %}` | Сортировка |
| `default` | `{{ wl.comment \| default('—') }}` | Значение по умолчанию |

> ❌ Небезопасные конструкции блокируются песочницей: доступ к атрибутам,
> выводящий за пределы графа объекта (`{{ config.__class__.__mro__ }}`),
> выбрасывает `SecurityError`. Это сделано намеренно.

### Минимальный пример

`~/.config/jira-tempo-mcp/templates/simple.j2`:

```jinja2
{# Минимальная сводка за неделю — использует worklogs, monday, friday, format_seconds #}
Неделя {{ format_date(monday) }} – {{ format_date(friday) }}
Всего: {{ format_seconds(worklogs | map(attribute='timeSpentSeconds') | sum) }}
Worklog-ов: {{ worklogs | length }}
```

Генерация:

```bash
generate_weekly_report(template="simple")
```

---

## 🐍 Шаблоны Python (`.py`)

Шаблон `.py` — это модуль Python, который выставляет атрибут **`TEMPLATE`**,
реализующий протокол `ReportTemplate`:

```python
class ReportTemplate(Protocol):
    name: str
    description: str
    def render(self, worklogs: list[dict], config: Config, **kwargs) -> str: ...
```

Модуль импортируется через `importlib`, и вызывается `TEMPLATE.render(...)`.
Тот же контекст, что и у Jinja2, передаётся ключевыми аргументами (`monday`,
`friday`, `issue_titles`, `users`, `per_user_worklogs`, `summary`, ...).

### Пример

`~/.config/jira-tempo-mcp/templates/my_report.py`:

```python
from collections import defaultdict

from jira_tempo_mcp.templates._shared import (
    extract_issue_key,
    extract_seconds,
    format_date,
)


class MyReport:
    name = "my_report"
    description = "Разбивка по задачам с итогами, отсортировано по времени."

    def render(self, worklogs, config, **kwargs):
        monday = kwargs.get("monday")
        friday = kwargs.get("friday")
        per_issue: dict[str, int] = defaultdict(int)
        for wl in worklogs:
            key = extract_issue_key(wl)
            if key:
                per_issue[key] += extract_seconds(wl)

        lines = [f"Неделя {format_date(monday)} – {format_date(friday)}", ""]
        for key, secs in sorted(per_issue.items(), key=lambda kv: kv[1], reverse=True):
            hours = secs / 3600
            lines.append(f"{key}: {hours:.1f}ч")
        return "\n".join(lines)


TEMPLATE = MyReport()
```

### ⚠️ Безопасность: только по явному включению

Шаблоны Python выполняют **произвольный код**. Они загружаются **только**
при `REPORT_TEMPLATE_ALLOW_PY=1`:

```bash
export REPORT_TEMPLATE_ALLOW_PY=1
```

Без этого флага каждый `.py` в директории шаблонов **пропускается** с
предупреждением. Предупреждение также пишется в лог при каждой загрузке —
как напоминание проверить файл. **Загружайте `.py`-шаблоны только из
доверенного источника.**

> Если модуль не загрузился (синтаксическая ошибка, нет `TEMPLATE`,
> нарушение протокола), он пропускается с предупреждением — остальной реестр
> продолжает работать. Один сломанный шаблон никогда не ломает генерацию
> отчёта.

---

## ⚙️ Справочник конфигурации

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `REPORT_TEMPLATE` | `default` | **Имя** шаблона для `generate_weekly_report` / `generate_team_report`. |
| `REPORT_TEMPLATE_PATH` | *(пусто)* | Явный **путь к файлу** шаблона (перекрывает `REPORT_TEMPLATE`). |
| `REPORT_TEMPLATE_DIR` | `~/.config/jira-tempo-mcp/templates/` | Директория для своих шаблонов. |
| `REPORT_TEMPLATE_ALLOW_PY` | `0` | Установите в `1`, чтобы включить `.py`-шаблоны (риск выполнения кода). |

Параметр **инструмента** `template` перекрывает `REPORT_TEMPLATE` для
одного вызова. `REPORT_TEMPLATE_PATH` всегда приоритетнее, если задан.

---

## 🛠️ Поток работы: написать, предпросмотр, сгенерировать

1. **Напишите** файл `.j2` в директории шаблонов.
2. **Проверьте**, что он обнаружен:

   ```
   list_report_templates
   ```

3. **Предпросмотр** на тестовых данных (без записи файла):

   ```
   preview_report_template(template_name="standup", sample_data="default")
   ```

   `sample_data` — `default`, `minimal` или `empty`.

4. **Сгенерируйте** настоящий отчёт:

   ```
   generate_weekly_report(template="standup")
   ```

---

## 📚 Встроенные шаблоны

| Имя | Описание |
| --- | --- |
| `default` | Недельный отчёт, сгруппированный по задачам со стабильными секциями (исходная вёрстка). |
| `weekly_summary` | Компактная сводка: всего часов, топ-5 задач, без построчной детализации. |
| `team_report` | Командный отчёт: секции по пользователям + агрегированная сводка. |

Они доступны всегда; свои шаблоны добавляются рядом. Примеры отрисовки — в
[reports.ru.md](reports.ru.md#-пользовательские-шаблоны).

---

## ➡️ Дальше

- 📝 [reports.ru.md](reports.ru.md) — форматы отчётов (txt/md/json), карта секций, примеры.
- ⚙️ [configuration.ru.md](configuration.ru.md) — все переменные окружения.
- 🔌 [mcp-integration.ru.md](mcp-integration.ru.md) — инструменты MCP для работы с шаблонами.
