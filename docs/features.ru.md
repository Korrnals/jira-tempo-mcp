# ✨ Возможности — что умеет jira-tempo-mcp

`jira-tempo-mcp` — один пакет с тремя лицами: **MCP-сервер** с 19
инструментами поверх самохостинг-инстанса Jira (Server / Data Center) +
Tempo Timesheets 4, **CLI** (`jira-tempo-mcp`) для установки, обновления и
управления специалистом, и **standalone AI-агент-специалист**, который
дергает генераторы отчётов сервера из Copilot Chat и других оболочек.

Эта страница — карта возможностей. Полный справочник инструментов с
параметрами и примерами живёт в [api.ru.md](api.ru.md).

---

## 🗺️ В двух словах

| Группа возможностей | Инструменты | Подробнее |
| --- | --- | --- |
| 🔍 [Чтение Jira и Tempo](#-чтение-jira-и-tempo) | 8 | [api.ru.md](api.ru.md) |
| ⏱️ [Учёт времени](#-учёт-времени) | 2 | [api.ru.md](api.ru.md) |
| 🧩 [Создание задач и декомпозиция по шаблонам](#-создание-задач-и-декомпозиция-по-шаблонам) | 4 | [task-templates.ru.md](task-templates.ru.md) |
| 📊 [Отчёты](#-отчёты) | 5 | [reports.ru.md](reports.ru.md), [templates.ru.md](templates.ru.md) |
| 🖥️ [CLI и операции](#-cli-и-операции) | 5 команд | [cli.ru.md](cli.ru.md) |
| 🤖 [AI-агент-специалист](#-ai-агент-специалист) | — | [README §Агент JTM](../README.ru.md#-агент-jtm-standalone-агент-для-copilot-chat) |

---

## 🔍 Чтение Jira и Tempo

Инструменты только для чтения — фундамент, на котором строятся все отчёты.

| Инструмент | Что делает |
| --- | --- |
| [`get_issue`](api.ru.md#-get_issue) | Метаданные задачи: summary, статус, проект |
| [`list_issues_by_jql`](api.ru.md#-list_issues_by_jql) | Поиск задач по JQL (только чтение, до 100 результатов) |
| [`list_worklogs`](api.ru.md#-list_worklogs) | Worklog'и Tempo за период или один день |
| [`get_worklog`](api.ru.md#-get_worklog) | Один worklog по Tempo ID |
| [`list_favorite_issues`](api.ru.md#-list_favorite_issues) | Избранные задачи текущего пользователя |
| [`list_user_tasks`](api.ru.md#-list_user_tasks) | Задачи пользователя со статусом, приоритетом, комментариями |
| [`search_users`](api.ru.md#-search_users) | Поиск пользователей Jira по имени, фамилии или username |
| [`get_current_user`](api.ru.md#-get_current_user) | Информация об аутентифицированном пользователе (владельце PAT) |

---

## ⏱️ Учёт времени

| Инструмент | Что делает |
| --- | --- |
| [`create_worklog`](api.ru.md#-create_worklog) | Учесть время на задаче Jira, с комментарием |
| [`delete_worklog`](api.ru.md#-delete_worklog) | Удалить worklog (отмена неправильно учтённого времени) |

---

## 🧩 Создание задач и декомпозиция по шаблонам

| Инструмент | Что делает |
| --- | --- |
| [`create_issue`](api.ru.md#-create_issue) | Создать задачу Jira — в том числе подзадачу через ключ родителя |
| [`add_issue_comment`](api.ru.md#-add_issue_comment) | Добавить комментарий к существующей задаче |
| [`list_issue_templates`](api.ru.md#-list_issue_templates) | Показать доступные шаблоны задач (встроенные + пользовательские) |
| [`create_issue_from_template`](api.ru.md#-create_issue_from_template) | Создать одну родительскую задачу и упорядоченный список дочерних подзадач из YAML-шаблона |

**Шаблон задач** разворачивается в родительскую задачу и упорядоченный
список дочерних подзадач — повторяемый чеклист одним вызовом. В пакет
встроен шаблон `stand-preparation` (15 дочерних задач); свои YAML-файлы
переопределяют встроенные или добавляют новые через переменную окружения
`JTM_TEMPLATES_DIR`. Поля шаблона рендерятся в песочнице Jinja2 с
контекстом (`summary`, `user_description`, `project_key`, `today`).

Формат, правила валидации и пример: [task-templates.ru.md](task-templates.ru.md).

---

## 📊 Отчёты

Три генератора, каждый умеет `txt`, `md` и `json`:

| Инструмент | Что делает |
| --- | --- |
| [`generate_weekly_report`](api.ru.md#-generate_weekly_report) | Еженедельный отчёт из worklog'ов Tempo |
| [`generate_team_report`](api.ru.md#-generate_team_report) | Командный отчёт по нескольким пользователям Jira |
| [`generate_tasks_report`](api.ru.md#-generate_tasks_report) | Отчёт по задачам с группировкой по статусам — по одному пользователю (индивидуальный режим) или по нескольким (групповой режим, только активные задачи — определяется по не зависящему от языка `statusCategory`) |

Шаблоны и обвязка вокруг них:

| Инструмент | Что делает |
| --- | --- |
| [`list_report_templates`](api.ru.md#-list_report_templates) | Показать доступные шаблоны отчётов (встроенные + пользовательские) |
| [`preview_report_template`](api.ru.md#-preview_report_template) | Отрисовать шаблон на образцовых данных — без вызова Jira, без записи файла |

**Пользовательские шаблоны отчётов**: положите файл `.j2` или `.py` в
каталог шаблонов — и он становится доступным по имени. Jinja2 работает в
песочнице; Python-шаблоны включаются явно (`REPORT_TEMPLATE_ALLOW_PY=1`).

Форматы отчётов и маппинг секций: [reports.ru.md](reports.ru.md).
Справочник для авторов шаблонов: [templates.ru.md](templates.ru.md).

---

## 🖥️ CLI и операции

Консольный скрипт `jira-tempo-mcp` диспетчеризует пять подкоманд (плюс
`--version` / `--help`):

| Команда | Что делает |
| --- | --- |
| `serve` | Запустить MCP-сервер через stdio (по умолчанию) |
| `install` | Интерактивный установщик (venv + `.env` + VS Code) |
| `uninstall` | Откатить установку |
| `update` | Самообновление; определяет режим установки (wheel / editable); автообновляет установленного специалиста |
| `install-specialist` | Установить AI-специалиста в AI-оболочки |

`install-specialist` знает реестр оболочек: `copilot`, `zcode`, `claude`,
`pi`, `hermes` и `opencode` поддерживаются, `codex` пропускается (нет
конвенции файлов агента). Оболочки «только skills» (`claude`, `pi`,
`hermes`, `opencode`) не получают файла агента — VS Code кросс-сканирует
каталог агентов claude, и файл агента JTM там породил бы дублирующуюся
запись в picker'е. Каждая установка записывает имена оболочек в файл
состояния; `update` после успешного обновления пакета переустанавливает
специалиста из новых данных.

Справочник команд: [cli.ru.md](cli.ru.md). Способы установки: [installation.ru.md](installation.ru.md).

---

## 🤖 AI-агент-специалист

Standalone-агент — **JTM: Jira Tempo Reports** — который предсказуемо строит
отчёты по Jira/Tempo, вызывая генераторы сервера. Работает в Copilot Chat
(графический пикер, недельный отчёт в один клик), ZCode, Claude Code, pi,
Hermes, OpenCode и других оболочках с поддержкой MCP. Поставляется внутри
wheel: переустановить его в любой момент можно командой `install-specialist`,
git clone не нужен.

Подробности: [README §Агент JTM](../README.ru.md#-агент-jtm-standalone-агент-для-copilot-chat),
таблица оболочек в [cli.ru.md](cli.ru.md#-install-specialist).

---

## ⚠️ Ограничения

- **E2E против реального Jira — только чтение, по политике.** Инструменты
  записи (`create_worklog`, `delete_worklog`, `create_issue`,
  `add_issue_comment`, `create_issue_from_template`) существуют и покрыты
  unit-тестами на mock-транспорте; live-проверку записи на реальном
  инстансе сознательно не выполняем.
- **JQL-поиск ограничен 100 результатами** на один вызов `list_issues_by_jql`.

---

## ➡️ Дальнейшие шаги

- 🌐 [api.ru.md](api.ru.md) — полный справочник инструментов; эта страница —
  карта, а не справочник
- 📦 [installation.ru.md](installation.ru.md) — режимы установки и walkthrough
- ⚙️ [configuration.ru.md](configuration.ru.md) — переменные окружения
