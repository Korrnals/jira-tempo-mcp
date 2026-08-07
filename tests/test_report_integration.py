"""Integration tests for generate_weekly_report with a mocked JiraTempoClient.

Verifies the full flow: fetch worklogs → group by issue → write file → verify content.
The client is mocked with unittest.mock.AsyncMock — no real HTTP calls, no real
credentials, no .env reads.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from jira_tempo_mcp.client import JiraTempoClient
from jira_tempo_mcp.config import Config
from jira_tempo_mcp.report import generate_weekly_report

# Target week: Monday 2026-06-15 — Friday 2026-06-19.
TARGET_DATE = date(2026, 6, 17)  # Wednesday
EXPECTED_FILENAME = "testuser_2026-06-15_2026-06-19.txt"


# --- Helpers -----------------------------------------------------------------


def _make_config(**overrides: Any) -> Config:
    """Build a Config with test values — never reads .env or real credentials."""
    defaults: dict[str, Any] = {
        "jira_base_url": "https://jira.test.example",
        "jira_user": "testuser",
        "jira_pat": "fake-pat-for-testing",
        "author_display_name": "Тестовый Пользователь",
        "section_map": {
            "PROJECT-100": "Section A",
            "PROJECT-102": "Section C",
            "PROJECT-101": "Section B",
        },
        "stable_order": ["PROJECT-100", "PROJECT-102", "PROJECT-101"],
        "non_issue_sections": [
            "Team meetings and syncs.",
            "Jira triage and admin.",
        ],
    }
    defaults.update(overrides)
    return Config(**defaults)


def _make_worklog(
    issue_key: str,
    seconds: int,
    day: int,
    comment: str = "",
) -> dict[str, Any]:
    """Build a fake Tempo worklog dict for the target week (June 2026)."""
    wl: dict[str, Any] = {
        "issueKey": issue_key,
        "timeSpentSeconds": seconds,
        "startDate": f"2026-06-{day:02d}",
    }
    if comment:
        wl["comment"] = comment
    return wl


def _make_mock_client(
    worklogs: list[dict[str, Any]],
    issue_summaries: dict[str, str] | None = None,
) -> AsyncMock:
    """Create a mocked JiraTempoClient — no real HTTP calls.

    find_worker_key → "worker123"
    search_worklogs → the provided worklog list
    get_issue → issue metadata with summary from issue_summaries (or key as fallback)
    """
    mock = AsyncMock(spec=JiraTempoClient)
    mock.find_worker_key.return_value = "worker123"
    mock.search_worklogs.return_value = worklogs

    async def _get_issue(key: str) -> dict[str, Any]:
        summary = (issue_summaries or {}).get(key, f"Summary for {key}")
        return {"key": key, "fields": {"summary": summary}}

    mock.get_issue.side_effect = _get_issue
    return mock


# --- Test classes ------------------------------------------------------------


class TestGenerateWeeklyReportBasic:
    """Basic file creation and path verification."""

    async def test_generate_report_basic(self, tmp_path: Path) -> None:
        worklogs = [
            _make_worklog("PROJECT-100", 3600, 15, "Stand support"),
        ]
        config = _make_config()
        mock_client = _make_mock_client(worklogs)

        result = await generate_weekly_report(
            cast(JiraTempoClient, mock_client),
            config,
            target_date=TARGET_DATE,
            output_dir=tmp_path,
        )

        expected_path = tmp_path / EXPECTED_FILENAME
        assert result == str(expected_path)
        assert expected_path.exists()
        assert expected_path.is_file()

        # Worker key resolution and worklog search called with right args.
        mock_client.find_worker_key.assert_called_once_with("testuser")
        mock_client.search_worklogs.assert_called_once_with(
            "2026-06-15", "2026-06-19", worker_keys=["worker123"]
        )


class TestGenerateWeeklyReportContent:
    """Report header, dates, and section structure."""

    async def test_generate_report_content(self, tmp_path: Path) -> None:
        worklogs = [
            _make_worklog("PROJECT-100", 3600, 15, "Stand support"),
            _make_worklog("PROJECT-102", 7200, 16, ""),
        ]
        config = _make_config()
        mock_client = _make_mock_client(worklogs)

        result = await generate_weekly_report(
            cast(JiraTempoClient, mock_client),
            config,
            target_date=TARGET_DATE,
            output_dir=tmp_path,
        )
        content = Path(result).read_text(encoding="utf-8")

        # Header has author name.
        assert "Тестовый Пользователь" in content
        # Header has formatted date range.
        assert "15.06.2026" in content
        assert "19.06.2026" in content
        # Stable section titles present.
        assert "Section A" in content
        # Non-issue sections present.
        assert "Team meetings and syncs." in content
        assert "Jira triage and admin." in content
        # Comment from worklog appears.
        assert "Stand support" in content
        # Worklog without comment shows formatted time.
        assert "2h отработано" in content


class TestGenerateWeeklyReportStableSections:
    """Stable sections appear in the configured order."""

    async def test_generate_report_stable_sections(self, tmp_path: Path) -> None:
        # Provide worklogs for 3 stable keys (intentionally out of order).
        worklogs = [
            _make_worklog("PROJECT-101", 3600, 17, "Review PR"),
            _make_worklog("PROJECT-100", 7200, 15, "Stand support"),
            _make_worklog("PROJECT-102", 3600, 16, "Design doc"),
        ]
        config = _make_config()
        mock_client = _make_mock_client(worklogs)

        result = await generate_weekly_report(
            cast(JiraTempoClient, mock_client),
            config,
            target_date=TARGET_DATE,
            output_dir=tmp_path,
        )
        content = Path(result).read_text(encoding="utf-8")

        # Stable order from config: 100, 102, 101.
        # Only 100, 102, 101 have worklogs → appear in that order.
        pos_100 = content.index("PROJECT-100")
        pos_102 = content.index("PROJECT-102")
        pos_101 = content.index("PROJECT-101")
        assert pos_100 < pos_102 < pos_101

        # Stable keys are in section_map → get_issue never called.
        mock_client.get_issue.assert_not_called()


class TestGenerateWeeklyReportUnknownIssues:
    """Unknown issues appear after non-issue sections, sorted by total time desc."""

    async def test_generate_report_unknown_issues(self, tmp_path: Path) -> None:
        worklogs = [
            _make_worklog("PROJECT-200", 3600, 15, ""),  # 1h
            _make_worklog("PROJECT-201", 7200, 16, ""),  # 2h
            _make_worklog("PROJECT-202", 1800, 17, ""),  # 30m
        ]
        summaries = {
            "PROJECT-200": "Task A",
            "PROJECT-201": "Task B",
            "PROJECT-202": "Task C",
        }
        config = _make_config()
        mock_client = _make_mock_client(worklogs, issue_summaries=summaries)

        result = await generate_weekly_report(
            cast(JiraTempoClient, mock_client),
            config,
            target_date=TARGET_DATE,
            output_dir=tmp_path,
        )
        content = Path(result).read_text(encoding="utf-8")

        # Unknown issues sorted by total time desc: 201 (2h), 200 (1h), 202 (30m).
        pos_201 = content.index("PROJECT-201")
        pos_200 = content.index("PROJECT-200")
        pos_202 = content.index("PROJECT-202")
        assert pos_201 < pos_200 < pos_202

        # Unknown issues come after non-issue sections.
        pos_planerki = content.index("Team meetings and syncs.")
        assert pos_planerki < pos_201

        # Summaries fetched from Jira appear in the report.
        assert "Task B" in content
        assert "Task A" in content
        assert "Task C" in content

        # get_issue called once per unknown key.
        assert mock_client.get_issue.call_count == 3


class TestGenerateWeeklyReportCustomOutputDir:
    """output_dir parameter overrides config.report_output_dir."""

    async def test_generate_report_custom_output_dir(self, tmp_path: Path) -> None:
        worklogs = [_make_worklog("PROJECT-100", 3600, 15, "Stand")]
        # Set a config output dir that should NOT be used.
        config = _make_config(report_output_dir=str(tmp_path / "config_dir"))
        mock_client = _make_mock_client(worklogs)

        custom_dir = tmp_path / "custom_output"
        result = await generate_weekly_report(
            cast(JiraTempoClient, mock_client),
            config,
            target_date=TARGET_DATE,
            output_dir=custom_dir,
        )

        expected_path = custom_dir / EXPECTED_FILENAME
        assert result == str(expected_path)
        assert expected_path.exists()
        # Config dir should NOT have been created.
        assert not (tmp_path / "config_dir").exists()


class TestGenerateWeeklyReportEmptyWeek:
    """No worklogs → report still generated with header + non-issue sections only."""

    async def test_generate_report_empty_week(self, tmp_path: Path) -> None:
        worklogs: list[dict[str, Any]] = []
        config = _make_config()
        mock_client = _make_mock_client(worklogs)

        result = await generate_weekly_report(
            cast(JiraTempoClient, mock_client),
            config,
            target_date=TARGET_DATE,
            output_dir=tmp_path,
        )
        content = Path(result).read_text(encoding="utf-8")

        # File is created.
        assert Path(result).exists()

        # Header present with author and dates.
        assert "Тестовый Пользователь" in content
        assert "15.06.2026" in content
        assert "19.06.2026" in content

        # Non-issue sections present.
        assert "Team meetings and syncs." in content
        assert "Jira triage and admin." in content

        # No issue keys in the report.
        assert "PROJECT-" not in content

        # find_worker_key still called (author_filter is None).
        mock_client.find_worker_key.assert_called_once_with("testuser")
        # get_issue never called (no worklogs to group).
        mock_client.get_issue.assert_not_called()


# --- Format parameter tests (v0.3.0) ---


class TestGenerateWeeklyReportMarkdown:
    """Markdown format: .md extension, tables, bold formatting."""

    async def test_md_format(self, tmp_path: Path) -> None:
        worklogs = [
            _make_worklog("PROJECT-100", 3600, 15, "Stand support"),
            _make_worklog("PROJECT-200", 7200, 16, "Debug"),
        ]
        config = _make_config()
        mock_client = _make_mock_client(worklogs, {"PROJECT-200": "Task B"})

        result = await generate_weekly_report(
            cast(JiraTempoClient, mock_client),
            config,
            target_date=TARGET_DATE,
            output_dir=tmp_path,
            fmt="md",
        )

        path = Path(result)
        assert path.suffix == ".md"
        content = path.read_text(encoding="utf-8")
        # Markdown header (new table-based format).
        assert content.startswith("# Отчёт за неделю")
        assert "15.06.2026" in content
        assert "19.06.2026" in content
        # Markdown table with worklogs as rows.
        assert "| Ключ | Задача | Часы | Комментарий |" in content
        assert "|------|--------|------:|-------------|" in content
        # Bold total row at the bottom.
        assert "**3h**" in content
        assert "**Сотрудник:**" in content
        assert "**Всего:**" in content

    async def test_md_default_is_txt(self, tmp_path: Path) -> None:
        """Default format is txt (backward compatible)."""
        worklogs = [_make_worklog("PROJECT-100", 3600, 15, "Stand")]
        config = _make_config()
        mock_client = _make_mock_client(worklogs)

        result = await generate_weekly_report(
            cast(JiraTempoClient, mock_client),
            config,
            target_date=TARGET_DATE,
            output_dir=tmp_path,
        )

        assert Path(result).suffix == ".txt"


class TestGenerateWeeklyReportJSON:
    """JSON format: .json extension, structured data."""

    async def test_json_format(self, tmp_path: Path) -> None:
        worklogs = [
            _make_worklog("PROJECT-100", 3600, 15, "Stand support"),
            _make_worklog("PROJECT-200", 7200, 16, "Debug"),
        ]
        config = _make_config()
        mock_client = _make_mock_client(worklogs, {"PROJECT-200": "Task B"})

        result = await generate_weekly_report(
            cast(JiraTempoClient, mock_client),
            config,
            target_date=TARGET_DATE,
            output_dir=tmp_path,
            fmt="json",
        )

        path = Path(result)
        assert path.suffix == ".json"
        import json as _json

        data = _json.loads(path.read_text(encoding="utf-8"))
        assert data["author"] == config.report_author_header
        assert data["date_from"] == "2026-06-15"
        assert data["date_to"] == "2026-06-19"
        assert data["total_seconds"] == 10800
        assert len(data["issues"]) >= 1

    async def test_invalid_format_raises(self, tmp_path: Path) -> None:
        worklogs = [_make_worklog("PROJECT-100", 3600, 15, "Stand")]
        config = _make_config()
        mock_client = _make_mock_client(worklogs)

        with pytest.raises(ValueError, match="Invalid format"):
            await generate_weekly_report(
                cast(JiraTempoClient, mock_client),
                config,
                target_date=TARGET_DATE,
                output_dir=tmp_path,
                fmt="xml",
            )


class TestGenerateWeeklyReportUsernameOverride:
    """Change 4: username override changes the report header and filename prefix.

    When ``username`` is provided, the report header author label and the
    filename prefix must reflect the override, not ``config.jira_user`` or
    ``config.report_author_header``.
    """

    async def test_username_override_header_and_filename(self, tmp_path: Path) -> None:
        worklogs = [_make_worklog("PROJECT-100", 3600, 15, "Stand support")]
        # Config uses jira_user="testuser", author_display_name="Тестовый Пользователь".
        config = _make_config()
        mock_client = _make_mock_client(worklogs)

        result = await generate_weekly_report(
            cast(JiraTempoClient, mock_client),
            config,
            target_date=TARGET_DATE,
            output_dir=tmp_path,
            username="otheruser",
        )

        # Filename uses the username override as prefix.
        expected_path = tmp_path / "otheruser_2026-06-15_2026-06-19.txt"
        assert result == str(expected_path)
        assert expected_path.exists()

        content = expected_path.read_text(encoding="utf-8")
        # Header shows the override username, not the configured display name.
        assert "otheruser" in content
        assert "Тестовый Пользователь" not in content

        # find_worker_key called with the override username, not config.jira_user.
        mock_client.find_worker_key.assert_called_once_with("otheruser")

    async def test_username_override_md_header(self, tmp_path: Path) -> None:
        """Markdown header also reflects the username override."""
        worklogs = [_make_worklog("PROJECT-100", 3600, 15, "Stand")]
        config = _make_config()
        mock_client = _make_mock_client(worklogs)

        result = await generate_weekly_report(
            cast(JiraTempoClient, mock_client),
            config,
            target_date=TARGET_DATE,
            output_dir=tmp_path,
            fmt="md",
            username="otheruser",
        )

        path = Path(result)
        assert path.name == "otheruser_2026-06-15_2026-06-19.md"
        content = path.read_text(encoding="utf-8")
        assert "**Сотрудник:** otheruser" in content
        assert "Тестовый Пользователь" not in content

    async def test_username_override_json_author(self, tmp_path: Path) -> None:
        """JSON format author field reflects the username override."""
        worklogs = [_make_worklog("PROJECT-100", 3600, 15, "Stand")]
        config = _make_config()
        mock_client = _make_mock_client(worklogs)

        result = await generate_weekly_report(
            cast(JiraTempoClient, mock_client),
            config,
            target_date=TARGET_DATE,
            output_dir=tmp_path,
            fmt="json",
            username="otheruser",
        )

        import json as _json

        data = _json.loads(Path(result).read_text(encoding="utf-8"))
        assert data["author"] == "otheruser"


class TestGenerateWeeklyReportSilentMkdir:
    """Problem 3 — output directories are created silently (no manual mkdir -p).

    When ``output_dir`` is not passed, ``generate_weekly_report`` derives the
    path from ``config.report_output_dir`` and builds the nested
    ``<root>/<year>/<month-ru>/weekly`` structure. The deeply-nested dirs must
    be created automatically via ``mkdir(parents=True, exist_ok=True)`` — this
    is the canonical-path fix that makes direct terminal Python calls work
    once ``config.report_output_dir`` is correctly populated from
    ``.env.local`` (problem 1).
    """

    async def test_silent_mkdir_from_config_output_dir(self, tmp_path: Path) -> None:
        """Nested year/month/weekly dirs auto-created from config.report_output_dir."""
        # Point report_output_dir at a non-existent nested path (no mkdir run yet).
        config = _make_config(report_output_dir=str(tmp_path / "canonical" / "reports"))
        mock_client = _make_mock_client([_make_worklog("PROJECT-100", 3600, 15, "Stand")])

        # Do NOT pass output_dir — force the function to derive it from config.
        result = await generate_weekly_report(
            cast(JiraTempoClient, mock_client),
            config,
            target_date=TARGET_DATE,
        )

        # Expected canonical layout: <root>/2026/июнь/weekly/<filename>
        expected_dir = tmp_path / "canonical" / "reports" / "2026" / "июнь" / "weekly"
        expected_path = expected_dir / EXPECTED_FILENAME
        assert result == str(expected_path)
        # The nested directory tree was created silently.
        assert expected_dir.is_dir()
        assert expected_path.is_file()

    async def test_silent_mkdir_idempotent_on_existing_dir(self, tmp_path: Path) -> None:
        """Re-running into an already-created dir does not raise (exist_ok)."""
        config = _make_config(report_output_dir=str(tmp_path / "reports"))
        mock_client = _make_mock_client([_make_worklog("PROJECT-100", 3600, 15, "Stand")])

        result1 = await generate_weekly_report(
            cast(JiraTempoClient, mock_client), config, target_date=TARGET_DATE
        )
        # Second run into the same (now-existing) nested dir must succeed.
        result2 = await generate_weekly_report(
            cast(JiraTempoClient, mock_client), config, target_date=TARGET_DATE
        )
        assert result1 == result2
        assert Path(result2).is_file()
