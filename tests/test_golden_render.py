"""Golden byte-identity gate for the default report renders.

Architectural Committee, wave "JTM feedback" (2026-10-30), contract §2 item 3:
the default txt/md/json render output on deterministic fixture worklogs is
frozen here BEFORE any wave change lands. Any slice that alters the default
render byte-for-byte (B3 live-preview, B4 include_dropped, ...) must keep
these tests green; a red golden is a blocking regression, not a snapshot to
refresh casually.

Render sites covered (contract §3):
- default template txt  → templates/builtin/default.py:94,126
- weekly md             → report.py:133
- team template txt     → templates/builtin/team_report.py:106,128
- team md               → team_report.py:321
Weekly/team JSON snapshots additionally pin the structured renders so the
B4 ``dropped`` field cannot appear by accident in default output.

Determinism: fixed June-2026 week, id-less worklogs (dedupe is a no-op),
titles resolved from section_map/get_issue mocks only, no wall-clock input
(target_date / date_from+date_to always explicit).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

from jira_tempo_mcp.client import JiraTempoClient
from jira_tempo_mcp.config import Config
from jira_tempo_mcp.report import generate_weekly_report
from jira_tempo_mcp.team_report import generate_team_report
from jira_tempo_mcp.templates.loader import build_registry

TARGET_DATE = date(2026, 6, 17)  # Wednesday of the fixture week
TEAM_DATE_FROM = "2026-06-15"
TEAM_DATE_TO = "2026-06-19"

# --- Fixture builders (mirror the captured golden run exactly) ---------------


def _make_config() -> Config:
    return Config(
        jira_base_url="https://jira.golden.example",
        jira_user="goldenuser",
        jira_pat="golden-fake-pat",
        author_display_name="Тестовый Автор",
        section_map={"PROJECT-100": "Section A", "PROJECT-102": "Section C"},
        stable_order=["PROJECT-100", "PROJECT-102"],
        non_issue_sections=["Планёрки и синки.", "Jira work."],
    )


def _wl(
    key: str | None,
    seconds: int,
    day: int,
    comment: str = "",
    author: str = "worker-a",
) -> dict[str, Any]:
    wl: dict[str, Any] = {
        "issueKey": key,
        "timeSpentSeconds": seconds,
        "startDate": f"2026-06-{day:02d}",
        "authorAccountId": author,
    }
    if comment:
        wl["comment"] = comment
    return wl


# Fixture comments deliberately include title echoes ("Section C", "Task Alpha")
# so every drop_lines_matching_title render site is exercised by the golden.
_WEEKLY_WORKLOGS = [
    _wl("PROJECT-100", 7200, 15, "Подготовка стенда"),
    _wl("PROJECT-100", 3600, 16, "Подготовка стенда\n- обновил чарт"),
    _wl("PROJECT-102", 5400, 17, "Section C"),
    _wl("PROJECT-200", 3600, 18, "Task Alpha"),
    _wl("PROJECT-200", 1800, 19, "Дебаг интеграции\nTask Alpha\nещё строка"),
    _wl(None, 1800, 16, "Daily standup"),
]

_TEAM_WORKLOGS: dict[str, list[dict[str, Any]]] = {
    "alice": [
        _wl("PROJECT-100", 7200, 15, "Section A", author="wk-alice"),
        _wl("PROJECT-200", 3600, 16, "Task Alpha", author="wk-alice"),
    ],
    "bob": [
        _wl("PROJECT-102", 5400, 17, "Section C\n- поправил доки", author="wk-bob"),
        _wl("PROJECT-201", 2700, 18, "Task Beta", author="wk-bob"),
    ],
}

_SUMMARIES = {"PROJECT-200": "Task Alpha", "PROJECT-201": "Task Beta"}


def _weekly_client() -> AsyncMock:
    mock = AsyncMock(spec=JiraTempoClient)
    mock.find_worker_key.return_value = "worker-a"
    mock.search_worklogs.return_value = _WEEKLY_WORKLOGS

    async def _get_issue(key: str) -> dict[str, Any]:
        return {"key": key, "fields": {"summary": _SUMMARIES.get(key, f"Summary for {key}")}}

    mock.get_issue.side_effect = _get_issue
    return mock


def _team_client() -> AsyncMock:
    mock = AsyncMock(spec=JiraTempoClient)
    mock.find_worker_key.side_effect = lambda u: f"wk-{u}"

    async def _search(
        date_from: str, date_to: str, worker_keys: list[str] | None = None
    ) -> list[dict[str, Any]]:
        user = (worker_keys or [""])[0].removeprefix("wk-")
        return _TEAM_WORKLOGS.get(user, [])

    mock.search_worklogs.side_effect = _search

    async def _get_issue(key: str) -> dict[str, Any]:
        return {"key": key, "fields": {"summary": _SUMMARIES.get(key, f"Summary for {key}")}}

    mock.get_issue.side_effect = _get_issue
    return mock


# --- Golden constants (captured 2026-10-30 from unmodified renders) ----------

GOLDEN_WEEKLY_TXT = """\
[Тестовый Автор] Отчет работы за неделю (15.06.2026 - 19.06.2026):

1. Section A [PROJECT-100]
\t+ Подготовка стенда
\t+ обновил чарт — 3h

2. Section C [PROJECT-102]
\t+ Section C — 1h 30m

3. Планёрки и синки.

4. Jira work.

5. [PROJECT-200] - "Task Alpha"
\t+ Task Alpha — 1h
\t+ Дебаг интеграции
\t+ ещё строка — 30m
"""

GOLDEN_WEEKLY_MD = """\
# Отчёт за неделю (15.06.2026 — 19.06.2026)

**Сотрудник:** Тестовый Автор
**Всего:** 6h

| Ключ | Задача | Часы | Комментарий |
|------|--------|------:|-------------|
| PROJECT-100 | Section A | 2h | Подготовка стенда |
| PROJECT-100 | Section A | 1h | • Подготовка стенда<br>• обновил чарт |
| PROJECT-102 | Section C | 1h 30m | Section C |
| PROJECT-200 | Task Alpha | 1h | Task Alpha |
| PROJECT-200 | Task Alpha | 30m | • Дебаг интеграции<br>• ещё строка |
| | | **6h** | |
"""

GOLDEN_WEEKLY_JSON = """\
{
  "author": "Тестовый Автор",
  "date_from": "2026-06-15",
  "date_to": "2026-06-19",
  "total_seconds": 21600,
  "total_human": "6h",
  "issues": [
    {
      "key": "PROJECT-100",
      "title": "Section A",
      "total_seconds": 10800,
      "total_human": "3h",
      "worklogs": [
        {
          "comment": "Подготовка стенда\\nобновил чарт",
          "seconds": 10800,
          "human": "3h"
        }
      ]
    },
    {
      "key": "PROJECT-102",
      "title": "Section C",
      "total_seconds": 5400,
      "total_human": "1h 30m",
      "worklogs": [
        {
          "comment": "Section C",
          "seconds": 5400,
          "human": "1h 30m"
        }
      ]
    },
    {
      "key": "PROJECT-200",
      "title": "Task Alpha",
      "total_seconds": 5400,
      "total_human": "1h 30m",
      "worklogs": [
        {
          "comment": "Task Alpha",
          "seconds": 3600,
          "human": "1h"
        },
        {
          "comment": "Дебаг интеграции\\nTask Alpha\\nещё строка",
          "seconds": 1800,
          "human": "30m"
        }
      ]
    }
  ]
}"""

GOLDEN_TEAM_TXT = """\
Командный отчёт за неделю (15.06.2026 - 19.06.2026):

== alice (3h) ==
  - PROJECT-100 (Section A):
      + Section A — 2h
  - PROJECT-200 (Task Alpha):
      + Task Alpha — 1h

== bob (2h 15m) ==
  - PROJECT-102 (Section C):
      + поправил доки — 1h 30m
  - PROJECT-201 (Task Beta):
      + Task Beta — 45m

== Сводка по команде ==
Всего отработано: 5h 15m

По сотрудникам:
  - alice: 3h
  - bob: 2h 15m

Топ-5 задач команды:
  - PROJECT-100 (Section A): 2h
  - PROJECT-102 (Section C): 1h 30m
  - PROJECT-200 (Task Alpha): 1h
  - PROJECT-201 (Task Beta): 45m
"""

GOLDEN_TEAM_MD = """\
# Командный отчёт за неделю (15.06.2026 — 19.06.2026)

## 📊 Сводка

| Сотрудник | Часы |
|-----------|------:|
| alice | 3h |
| bob | 2h 15m |
| **Итого** | **5h 15m** |

### 🏆 Топ-5 задач

| # | Ключ | Задача | Часы |
|---:|------|--------|------:|
| 1 | PROJECT-100 | Section A | 2h |
| 2 | PROJECT-102 | Section C | 1h 30m |
| 3 | PROJECT-200 | Task Alpha | 1h |
| 4 | PROJECT-201 | Task Beta | 45m |

---

## alice (3h)

| Ключ | Задача | Часы | Комментарий |
|------|--------|------:|-------------|
| PROJECT-100 | Section A | 2h | Section A |
| PROJECT-200 | Task Alpha | 1h | Task Alpha |
| | | **3h** | |

---

## bob (2h 15m)

| Ключ | Задача | Часы | Комментарий |
|------|--------|------:|-------------|
| PROJECT-102 | Section C | 1h 30m | поправил доки |
| PROJECT-201 | Task Beta | 45m | Task Beta |
| | | **2h 15m** | |
"""

GOLDEN_TEAM_JSON = """\
{
  "date_from": "2026-06-15",
  "date_to": "2026-06-19",
  "grand_total_seconds": 18900,
  "grand_total_human": "5h 15m",
  "per_user": [
    {
      "username": "alice",
      "display_name": "alice",
      "total_seconds": 10800,
      "total_human": "3h",
      "issues": [
        {
          "key": "PROJECT-100",
          "title": "Section A",
          "total_seconds": 7200,
          "total_human": "2h",
          "worklogs": [
            {
              "comment": "Section A",
              "seconds": 7200,
              "human": "2h"
            }
          ]
        },
        {
          "key": "PROJECT-200",
          "title": "Task Alpha",
          "total_seconds": 3600,
          "total_human": "1h",
          "worklogs": [
            {
              "comment": "Task Alpha",
              "seconds": 3600,
              "human": "1h"
            }
          ]
        }
      ]
    },
    {
      "username": "bob",
      "display_name": "bob",
      "total_seconds": 8100,
      "total_human": "2h 15m",
      "issues": [
        {
          "key": "PROJECT-102",
          "title": "Section C",
          "total_seconds": 5400,
          "total_human": "1h 30m",
          "worklogs": [
            {
              "comment": "Section C\\n- поправил доки",
              "seconds": 5400,
              "human": "1h 30m"
            }
          ]
        },
        {
          "key": "PROJECT-201",
          "title": "Task Beta",
          "total_seconds": 2700,
          "total_human": "45m",
          "worklogs": [
            {
              "comment": "Task Beta",
              "seconds": 2700,
              "human": "45m"
            }
          ]
        }
      ]
    }
  ],
  "top_issues": [
    {
      "key": "PROJECT-100",
      "title": "Section A",
      "seconds": 7200,
      "human": "2h"
    },
    {
      "key": "PROJECT-102",
      "title": "Section C",
      "seconds": 5400,
      "human": "1h 30m"
    },
    {
      "key": "PROJECT-200",
      "title": "Task Alpha",
      "seconds": 3600,
      "human": "1h"
    },
    {
      "key": "PROJECT-201",
      "title": "Task Beta",
      "seconds": 2700,
      "human": "45m"
    }
  ]
}"""


# --- Golden tests ------------------------------------------------------------


class TestGoldenDefaultRenders:
    """Byte-identity of the default renders (contract §2 item 3)."""

    async def test_weekly_txt_byte_identical(self, tmp_path: Path) -> None:
        """default template txt — drop sites default.py:94,126."""
        config = _make_config()
        registry = build_registry(config)
        path = await generate_weekly_report(
            cast(JiraTempoClient, _weekly_client()),
            config,
            target_date=TARGET_DATE,
            output_dir=tmp_path,
            fmt="txt",
            template=registry.get("default"),
        )
        assert Path(path).read_text(encoding="utf-8") == GOLDEN_WEEKLY_TXT

    async def test_weekly_md_byte_identical(self, tmp_path: Path) -> None:
        """Weekly Markdown — drop site report.py:133."""
        path = await generate_weekly_report(
            cast(JiraTempoClient, _weekly_client()),
            _make_config(),
            target_date=TARGET_DATE,
            output_dir=tmp_path,
            fmt="md",
        )
        assert Path(path).read_text(encoding="utf-8") == GOLDEN_WEEKLY_MD

    async def test_weekly_json_byte_identical(self, tmp_path: Path) -> None:
        """Weekly JSON must carry no extra top-level fields by default."""
        path = await generate_weekly_report(
            cast(JiraTempoClient, _weekly_client()),
            _make_config(),
            target_date=TARGET_DATE,
            output_dir=tmp_path,
            fmt="json",
        )
        assert Path(path).read_text(encoding="utf-8") == GOLDEN_WEEKLY_JSON

    async def test_team_txt_byte_identical(self, tmp_path: Path) -> None:
        """team_report template txt — drop sites builtin/team_report.py:106,128."""
        config = _make_config()
        registry = build_registry(config)
        result = await generate_team_report(
            cast(JiraTempoClient, _team_client()),
            config,
            ["alice", "bob"],
            date_from=TEAM_DATE_FROM,
            date_to=TEAM_DATE_TO,
            output_dir=tmp_path,
            fmt="txt",
            template=registry.get("team_report"),
        )
        assert result.file_path.read_text(encoding="utf-8") == GOLDEN_TEAM_TXT

    async def test_team_md_byte_identical(self, tmp_path: Path) -> None:
        """Team Markdown — drop site team_report.py:321."""
        result = await generate_team_report(
            cast(JiraTempoClient, _team_client()),
            _make_config(),
            ["alice", "bob"],
            date_from=TEAM_DATE_FROM,
            date_to=TEAM_DATE_TO,
            output_dir=tmp_path,
            fmt="md",
        )
        assert result.file_path.read_text(encoding="utf-8") == GOLDEN_TEAM_MD

    async def test_team_json_byte_identical(self, tmp_path: Path) -> None:
        """Team JSON must carry no extra top-level fields by default."""
        result = await generate_team_report(
            cast(JiraTempoClient, _team_client()),
            _make_config(),
            ["alice", "bob"],
            date_from=TEAM_DATE_FROM,
            date_to=TEAM_DATE_TO,
            output_dir=tmp_path,
            fmt="json",
        )
        assert result.file_path.read_text(encoding="utf-8") == GOLDEN_TEAM_JSON
