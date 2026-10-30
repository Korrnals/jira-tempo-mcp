# 🐛 Решение проблем

Частые ошибки и их исправление.

---

## 🔌 Диагностика подключения

MCP-клиент не видит сервер или не может вызвать инструменты? Пройдите
чек-лист сверху вниз — каждая категория снимает один класс сбоев.
**Сначала быстрый пинг:** вызовите
[`health_check`](api.ru.md#-health_check) — если он отвечает, процесс
сервера жив и API Jira/Tempo доступны, а проблема осталась в конфигурации
или на стороне клиента.

### 1. Процесс сервера

- [ ] Процесс запущен? В MCP-панели VS Code у сервера есть индикатор
      запуска; на хосте: `pgrep -af jira_tempo`.
- [ ] Падает при старте — прочитайте первые строки вывода: `ConfigError`
      или `ModuleNotFoundError` означают, что процесс умер до начала
      обслуживания (см. соответствующие разделы ниже).
- [ ] Недавно меняли `mcp.json`? Перезагрузите: `Ctrl+Shift+P → Developer:
      Reload Window`.

### 2. Команда запуска (stdio-транспорт)

- [ ] Сервер работает по **stdio** — сетевой порт он не открывает. Если
      MCP-клиент сообщает об ошибке соединения/порта, настоящая причина
      почти всегда — неверная пара `command`/`args` в `mcp.json`.
- [ ] `command` должен указывать на **venv-python** явно
      (`.../.venv/bin/python -m jira_tempo_mcp.server`) — системный python
      падает с `ModuleNotFoundError` (см. ниже).
- [ ] Для Docker-развёртывания проверьте, что контейнер поднят и MCP-клиент
      указывает на опубликованный endpoint.

### 3. Креденциалы и envFile-цепочка

Порядок разрешения конфига: **process env → `.env.local` (`envFile`) →
репо-`.env`** ([подробнее](configuration.ru.md#-приоритет-источников-конфигурации)).

- [ ] Все три обязательные переменные заданы: `JIRA_BASE_URL`, `JIRA_USER`,
      `JIRA_PAT`. Отсутствующая завершает работу с `ConfigError`, который
      называет переменную — но никогда её значение.
- [ ] `envFile` в `mcp.json` — **абсолютный путь** (`~` не разворачивается в
      sandbox-окружениях — см. ниже).
- [ ] ⚠️ **Гочик — stale env перебивает файл:** переменная, уже заданная в
      **окружении процесса** (блок `env` в `mcp.json`, shell, запускающий
      host, systemd), **сильнее** `.env.local`. Устаревший `JIRA_BASE_URL`,
      `JIRA_USER` или `REPORT_OUTPUT_DIR` там молчаливо перебивает
      отредактированный `.env.local`. Проверьте блок `env` на остатки
      старых значений, прежде чем править файл.

### 4. Сеть

- [ ] С того же хоста/контейнера, где работает сервер:
      `curl -I https://jira.example.com` — проверяет DNS, VPN и файрвол.
- [ ] За VPN? Процесс сервера наследует сеть того хоста, который его
      запустил — VPN в терминале автоматически не покрывает сервер,
      запущенный в другом месте.
- [ ] Вызовы уходят в таймаут, а не падают сразу → увеличьте
      `JIRA_HTTP_TIMEOUT` (по умолч. 30 с).

### Карта «симптом → категория»

| Симптом | Начните с |
| --- | --- |
| Сервера нет в MCP-панели | 1 (процесс) |
| `Failed to read envFile '~/...'` | 3 (envFile-цепочка) |
| `ConfigError` / `JIRA_BASE_URL or JIRA_PAT missing` | 3 (креденциалы) |
| Поправили `.env.local`, но действуют старые значения | 3 (гочик stale env) |
| `ModuleNotFoundError` при старте | 2 (команда запуска) |
| Вызовы инструментов уходят в таймаут | 4 (сеть) |

---

## 🐛 MCP-сервер не появляется в панели

**🩺 Симптом:** сервер `jira-tempo` отсутствует в MCP-панели VS Code.

**🔍 Причина:** VS Code не перечитал `mcp.json` после изменения.

**✅ Решение:**

```text
Ctrl+Shift+P → Developer: Reload Window
```

---

## ❌ `Failed to read envFile '~/...'`

**🩺 Симптом:** MCP-панель показывает `Failed to read envFile '~/.config/Code/User/.env.local'`.

**🔍 Причина:** VS Code MCP-host разворачивает `~` относительно своего
root-namespace, а не `$HOME` пользователя. Ломается в sandbox-окружениях
(distrobox, snap, flatpak, контейнеры).

**✅ Решение:** используйте **абсолютный путь** для `envFile` в `mcp.json`:

```json
"envFile": "/home/your-username/.config/Code/User/.env.local"
```

Для distrobox:

```json
"envFile": "/var/home/your-username/.distrobox/box/home/.config/Code/User/.env.local"
```

> 💡 **Совет:** См. [mcp-integration.ru.md](mcp-integration.ru.md#-абсолютные-пути-для-envfile-distrobox--контейнеры).

---

## ❌ `ModuleNotFoundError: No module named 'pytz'`

**🩺 Симптом:** сервер падает при запуске с `ModuleNotFoundError: No module
named 'pytz'` (или `mcp`, `httpx`, `pydantic`).

**🔍 Причина:** `python` в `mcp.json` — не venv-python; он обходит editable-установку
и её site-packages.

**✅ Решение:** укажите venv-python явно в `command`:

```json
"command": "${workspaceFolder}/.venv/bin/python"
```

Или в user-level конфиге:

```json
"command": "/home/your-username/projects/jira-tempo-mcp/.venv/bin/python"
```

> 💡 **Совет:** Переменная `PYTHONPATH` на `src/` — дополнительный фолбэк для
> окружений, переопределяющих `PYTHONHOME`.

---

## ❌ `400 Authorization header badly formatted`

**🩺 Симптом:** HTTP-type MCP-сервер (напр. GitHub MCP) возвращает
`400 Authorization header badly formatted`.

**🔍 Причина:** подстановка `${env:VAR}` не работает внутри `headers` для
HTTP-серверов.

**✅ Решение:** используйте `${input:...}` — он один раз запрашивает значение и
кэширует его в секретном хранилище VS Code. См.
[mcp-integration.ru.md](mcp-integration.ru.md#-input-для-http-серверов).

---

## ❌ `JIRA_BASE_URL or JIRA_PAT missing`

**🩺 Симптом:** сервер сразу завершается с
`JIRA_BASE_URL or JIRA_PAT missing` (`ConfigError` с backend-специфичными
рекомендациями).

**🔍 Причина:** обязательные переменные окружения не видны процессу сервера.

**✅ Решение:**

1. ✅ Проверьте, что `.env.local` существует и содержит `JIRA_PAT=...`.
2. ✅ Проверьте, что `envFile` в `mcp.json` указывает на правильный абсолютный путь.
3. ✅ Для CLI — проверьте, что `.env` в корне проекта содержит `JIRA_BASE_URL`,
   `JIRA_USER`, `JIRA_PAT`.
4. ✅ Перезапустите `python install.py`, чтобы перегенерировать `.env` и
   перерегистрировать конфиг VS Code.

> 💡 **Совет:** См. [configuration.ru.md](configuration.ru.md).

---

## ❌ `401 Unauthorized`

**🩺 Симптом:** вызовы инструментов возвращают `Jira/Tempo API error: 401 ...`.

**🔍 Причина:** PAT невалиден, истёк или отозван.

**✅ Решение:**

1. ✅ В Jira: Профиль → Personal Access Tokens → создать новый токен.
2. ✅ Обновите `JIRA_PAT` в `.env.local` (или `.env` для CLI).
3. ✅ Перезагрузите окно VS Code.

> 💡 **Совет:** Если используется отдельный `TEMPO_API_TOKEN`, перевыпустите и его.

---

## ❌ `Could not identify your Tempo worker key`

**🩺 Симптом:** `list_worklogs` или `generate_weekly_report` возвращают
`Could not identify your Tempo worker key`.

**🔍 Причина:** настроенный `JIRA_USER` не соответствует worker в Tempo, либо
нарушена связь с Tempo.

**✅ Решение:**

1. ✅ Проверьте, что `JIRA_USER` совпадает с логином Jira (с учётом регистра).
2. ✅ Убедитесь, что Tempo Timesheets 4 установлен и лицензирован на инстансе.
3. ✅ Проверьте `TEMPO_API_TOKEN` (если задан отдельно) — он должен быть
   валидным для Tempo.

---

## ❌ `output_dir '...' resolves outside the allowed root`

**🩺 Симптом:** `generate_weekly_report` возвращает
`output_dir '...' resolves outside the allowed root`.

**🔍 Причина:** аргумент `output_dir` разрешается за пределами
`REPORT_OUTPUT_DIR` (fallback-корень — `~/.mcp/jira-tempo-mcp/reports/`).
Это защита от path traversal.

**✅ Решение:** передавайте `output_dir` внутри разрешённого корня или задайте
`REPORT_OUTPUT_DIR` в нужную базовую директорию.

> 💡 **Совет:** См. [reports.ru.md](reports.ru.md#-защита-от-path-traversal).

---

## ❌ `Could not parse duration: '...'`

**🩺 Симптом:** `create_worklog` возвращает `Could not parse duration: '...'`.

**🔍 Причина:** в `time_spent` нет валидных токенов длительности.

**✅ Решение:** используйте поддерживаемые единицы: `w` (неделя), `d` (день),
`h` (час), `m` (минута).

| ✅ Валидно | ❌ Невалидно |
| --- | --- |
| `1h 30m` | `1:30` |
| `2h` | `2 hours` |
| `45m` | `45 minutes` |
| `1d 2h` | `1.5d` |

---

## ❌ `Invalid issue key '...'`

**🩺 Симптом:** `create_worklog` или `get_issue` возвращает `Invalid issue key '...'`.

**🔍 Причина:** ключ не соответствует `^[A-Z][A-Z0-9]+-\d+$`.

**✅ Решение:** используйте полный формат ключа Jira: `PROJECT-100`, а не
`project-100` или `PROJECT100`.

---

## ⏱️ Сервер стартует, но инструменты уходят в таймаут

**🩺 Симптом:** сервер запускается, но вызовы инструментов висят до истечения
`JIRA_HTTP_TIMEOUT` (по умолч. 30 с).

**🔍 Причина:** инстанс Jira недоступен из процесса сервера (файрвол, VPN, DNS).

**✅ Решение:**

1. ✅ Проверьте связь: `curl -I https://jira.example.com`.
2. ✅ Если за VPN — убедитесь, что VPN активен.
3. ✅ Увеличьте `JIRA_HTTP_TIMEOUT`, если инстанс Jira медленный.

---

## ➡️ Дальнейшие шаги

- 🔌 [mcp-integration.ru.md](mcp-integration.ru.md) — детали MCP-конфигурации
- ⚙️ [configuration.ru.md](configuration.ru.md) — все переменные окружения
- 🌐 [api.ru.md](api.ru.md#-обработка-ошибок) — справочник сообщений об ошибках
