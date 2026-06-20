# jira-tempo-mcp — Документация

![banner](assets/banner.svg)

MCP-сервер для **самохостинг-инстанса Jira (Server / Data Center) + Tempo Timesheets 4**.
Учитывайте время, просматривайте worklog'и и создавайте еженедельные отчёты
из вашего AI-агента (Copilot, Claude и др.) через Model Context Protocol.

## Быстрые ссылки

| Тема | Документ | Что вы узнаете |
| --- | --- | --- |
| Установка | [installation.ru.md](installation.ru.md) | `python install.py`, pip, Docker, venv |
| Настройка | [configuration.ru.md](configuration.ru.md) | переменные окружения, `.env.local`, `.env`, примеры |
| MCP-интеграция | [mcp-integration.ru.md](mcp-integration.ru.md) | VS Code `mcp.json`, `envFile`, workspace-конфиг |
| CLI | [cli.ru.md](cli.ru.md) | `serve`, `install`, `uninstall`, `--version` |
| API (MCP-инструменты) | [api.ru.md](api.ru.md) | `list_worklogs`, `create_worklog`, `generate_weekly_report`, … |
| Архитектура | [architecture.ru.md](architecture.ru.md) | слои, поток данных, модель безопасности |
| Отчёты | [reports.ru.md](reports.ru.md) | еженедельный отчёт, section mapping, стабильный порядок |
| Развёртывание | [deployment.ru.md](deployment.ru.md) | Docker, CI/CD, процесс релиза |
| Решение проблем | [troubleshooting.ru.md](troubleshooting.ru.md) | частые ошибки и их исправление |

## С чего начать

- **Впервые?** → [installation.ru.md](installation.ru.md) → [configuration.ru.md](configuration.ru.md) → [mcp-integration.ru.md](mcp-integration.ru.md)
- **Уже установлено?** → [api.ru.md](api.ru.md) — полный справочник инструментов
- **Что-то сломалось?** → [troubleshooting.ru.md](troubleshooting.ru.md)

## Язык

Русская версия — зеркальная. Основная (английская) документация: [README.md](README.md).

## Лицензия

MIT — см. корневой [README.ru.md](../README.ru.md#лицензия).
