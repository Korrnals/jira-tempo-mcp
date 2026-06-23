"""Tests for team_report.py — rate-limiting, per-user aggregation, 429 retry."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from jira_tempo_mcp.client import JiraTempoClient, JiraTempoError
from jira_tempo_mcp.config import Config
from jira_tempo_mcp.team_report import generate_team_report

TARGET_DATE = date(2026, 6, 17)  # Wednesday of the target week.


def _make_config(**overrides: Any) -> Config:
    defaults: dict[str, Any] = {
        "jira_base_url": "https://jira.test.example",
        "jira_user": "testuser",
        "jira_pat": "fake-pat-for-testing",
        "author_display_name": "Тестовый Пользователь",
        "section_map": {"PROJECT-100": "Section A"},
        "stable_order": ["PROJECT-100"],
        "non_issue_sections": [],
        "tempo_max_concurrent_requests": 3,
        "tempo_request_delay_ms": 0,
        "tempo_max_retries": 3,
    }
    defaults.update(overrides)
    return Config(**defaults)


def _make_worklog(issue_key: str, seconds: int, day: int, comment: str = "") -> dict[str, Any]:
    wl: dict[str, Any] = {
        "issueKey": issue_key,
        "timeSpentSeconds": seconds,
        "startDate": f"2026-06-{day:02d}",
    }
    if comment:
        wl["comment"] = comment
    return wl


def _make_mock_client(
    user_worklogs: dict[str, list[dict[str, Any]]],
    issue_summaries: dict[str, str] | None = None,
) -> AsyncMock:
    """Mock client: find_worker_key per user, search_worklogs per call."""
    mock = AsyncMock(spec=JiraTempoClient)

    async def _find_worker_key(username: str | None = None) -> str:
        return f"worker-{username or 'default'}"

    async def _search_worklogs(
        date_from: str,
        date_to: str,
        *,
        worker_keys: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        # Map worker key back to username.
        if not worker_keys:
            return []
        wk = worker_keys[0]
        username = wk.replace("worker-", "") if wk.startswith("worker-") else wk
        return user_worklogs.get(username, [])

    async def _get_issue(key: str) -> dict[str, Any]:
        summary = (issue_summaries or {}).get(key, f"Summary for {key}")
        return {"key": key, "fields": {"summary": summary}}

    mock.find_worker_key.side_effect = _find_worker_key
    mock.search_worklogs.side_effect = _search_worklogs
    mock.get_issue.side_effect = _get_issue
    return mock


class TestTeamReportBasic:
    """Two users with worklogs → file + summary."""

    async def test_two_users_with_worklogs(self, tmp_path: Path) -> None:
        user_worklogs = {
            "alice": [
                _make_worklog("PROJECT-100", 3600, 15, "Alice on A"),
                _make_worklog("PROJECT-200", 7200, 16, ""),
            ],
            "bob": [
                _make_worklog("PROJECT-100", 1800, 17, "Bob on A"),
                _make_worklog("PROJECT-300", 5400, 18, ""),
            ],
        }
        config = _make_config()
        mock_client = _make_mock_client(
            user_worklogs, {"PROJECT-200": "Task B", "PROJECT-300": "Task C"}
        )

        result = await generate_team_report(
            cast(JiraTempoClient, mock_client),
            config,
            users=["alice", "bob"],
            date_from="2026-06-15",
            date_to="2026-06-19",
            output_dir=tmp_path,
        )

        assert result.file_path.exists()
        content = result.file_path.read_text(encoding="utf-8")
        # Per-user sections present.
        assert "alice" in content
        assert "bob" in content
        # Aggregate summary present.
        assert "Сводка по команде" in content
        # Grand total = 3600 + 7200 + 1800 + 5400 = 18000s = 5h.
        assert "5h" in content
        # Per-user totals in summary.
        assert "alice" in result.summary
        assert "bob" in result.summary
        # per_user_totals dict.
        assert result.per_user_totals["alice"] == 10800
        assert result.per_user_totals["bob"] == 7200


class TestTeamReportEmptyUser:
    """One user with worklogs, one without — empty user noted in summary."""

    async def test_one_empty_user(self, tmp_path: Path) -> None:
        user_worklogs = {
            "alice": [_make_worklog("PROJECT-100", 3600, 15, "Alice on A")],
            "bob": [],
        }
        config = _make_config()
        mock_client = _make_mock_client(user_worklogs)

        result = await generate_team_report(
            cast(JiraTempoClient, mock_client),
            config,
            users=["alice", "bob"],
            date_from="2026-06-15",
            date_to="2026-06-19",
            output_dir=tmp_path,
        )

        content = result.file_path.read_text(encoding="utf-8")
        assert "Без отработанного времени" in content
        assert "bob" in content
        assert result.per_user_totals["bob"] == 0
        assert result.per_user_totals["alice"] == 3600


class TestTeamReportRateLimiting:
    """Semaphore limits concurrency."""

    async def test_semaphore_limits_concurrency(self, tmp_path: Path) -> None:
        # Track concurrent calls.
        concurrent = 0
        max_concurrent = 0
        lock = asyncio.Lock()

        mock = AsyncMock(spec=JiraTempoClient)

        async def _find_worker_key(username: str | None = None) -> str:
            return f"worker-{username}"

        async def _search_worklogs(
            date_from: str,
            date_to: str,
            *,
            worker_keys: list[str] | None = None,
        ) -> list[dict[str, Any]]:
            nonlocal concurrent, max_concurrent
            async with lock:
                concurrent += 1
                max_concurrent = max(max_concurrent, concurrent)
            await asyncio.sleep(0.05)  # simulate latency
            async with lock:
                concurrent -= 1
            return []

        async def _get_issue(key: str) -> dict[str, Any]:
            return {"key": key, "fields": {"summary": key}}

        mock.find_worker_key.side_effect = _find_worker_key
        mock.search_worklogs.side_effect = _search_worklogs
        mock.get_issue.side_effect = _get_issue

        # 6 users, concurrency=2 → max concurrent should be <= 2.
        config = _make_config(tempo_max_concurrent_requests=2, tempo_request_delay_ms=0)
        users = ["u1", "u2", "u3", "u4", "u5", "u6"]

        await generate_team_report(
            cast(JiraTempoClient, mock),
            config,
            users=users,
            date_from="2026-06-15",
            date_to="2026-06-19",
            output_dir=tmp_path,
        )

        assert max_concurrent <= 2, f"concurrency exceeded limit: {max_concurrent}"


class TestTeamReport429Retry:
    """429 on first attempt → retry succeeds."""

    async def test_429_retry_then_success(self, tmp_path: Path) -> None:
        call_count = 0

        mock = AsyncMock(spec=JiraTempoClient)

        async def _find_worker_key(username: str | None = None) -> str:
            return f"worker-{username}"

        async def _search_worklogs(
            date_from: str,
            date_to: str,
            *,
            worker_keys: list[str] | None = None,
        ) -> list[dict[str, Any]]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise JiraTempoError("API error 429 from tempo: Too Many Requests")
            return [_make_worklog("PROJECT-100", 3600, 15, "retry ok")]

        async def _get_issue(key: str) -> dict[str, Any]:
            return {"key": key, "fields": {"summary": key}}

        mock.find_worker_key.side_effect = _find_worker_key
        mock.search_worklogs.side_effect = _search_worklogs
        mock.get_issue.side_effect = _get_issue

        config = _make_config(tempo_max_retries=3, tempo_request_delay_ms=0)
        result = await generate_team_report(
            cast(JiraTempoClient, mock),
            config,
            users=["alice"],
            date_from="2026-06-15",
            date_to="2026-06-19",
            output_dir=tmp_path,
        )

        assert call_count == 2  # first failed, second succeeded
        assert result.per_user_totals["alice"] == 3600

    async def test_429_exhausted_raises(self, tmp_path: Path) -> None:
        mock = AsyncMock(spec=JiraTempoClient)

        async def _find_worker_key(username: str | None = None) -> str:
            return f"worker-{username}"

        async def _search_worklogs(
            date_from: str,
            date_to: str,
            *,
            worker_keys: list[str] | None = None,
        ) -> list[dict[str, Any]]:
            raise JiraTempoError("API error 429 from tempo: Too Many Requests")

        async def _get_issue(key: str) -> dict[str, Any]:
            return {"key": key, "fields": {"summary": key}}

        mock.find_worker_key.side_effect = _find_worker_key
        mock.search_worklogs.side_effect = _search_worklogs
        mock.get_issue.side_effect = _get_issue

        config = _make_config(tempo_max_retries=2, tempo_request_delay_ms=0)
        # The error is caught and recorded — user gets empty worklogs, not a crash.
        result = await generate_team_report(
            cast(JiraTempoClient, mock),
            config,
            users=["alice"],
            date_from="2026-06-15",
            date_to="2026-06-19",
            output_dir=tmp_path,
        )
        # User recorded with 0 total; file still written.
        assert result.per_user_totals["alice"] == 0
        assert result.file_path.exists()


class TestTeamReportValidation:
    """Empty users list raises ValueError."""

    async def test_empty_users_raises(self, tmp_path: Path) -> None:
        config = _make_config()
        mock_client = _make_mock_client({})
        with pytest.raises(ValueError, match="non-empty"):
            await generate_team_report(
                cast(JiraTempoClient, mock_client),
                config,
                users=[],
                output_dir=tmp_path,
            )

    async def test_invalid_format_raises(self, tmp_path: Path) -> None:
        config = _make_config()
        mock_client = _make_mock_client({"alice": []})
        with pytest.raises(ValueError, match="Invalid format"):
            await generate_team_report(
                cast(JiraTempoClient, mock_client),
                config,
                users=["alice"],
                output_dir=tmp_path,
                fmt="xml",
            )


# --- Format parameter tests (v0.3.0) ---


class TestTeamReportMarkdown:
    """Markdown format: .md extension, tables, bold formatting."""

    async def test_md_format(self, tmp_path: Path) -> None:
        user_worklogs = {
            "alice": [_make_worklog("PROJECT-100", 3600, 15, "Alice on A")],
            "bob": [_make_worklog("PROJECT-200", 7200, 16, "Bob on B")],
        }
        config = _make_config()
        mock_client = _make_mock_client(
            user_worklogs, {"PROJECT-200": "Task B"}
        )

        result = await generate_team_report(
            cast(JiraTempoClient, mock_client),
            config,
            users=["alice", "bob"],
            date_from="2026-06-15",
            date_to="2026-06-19",
            output_dir=tmp_path,
            fmt="md",
        )

        assert result.file_path.suffix == ".md"
        content = result.file_path.read_text(encoding="utf-8")
        assert content.startswith("# Командный отчёт")
        # New table-based format: summary table at top, per-user tables.
        assert "## 📊 Сводка" in content
        assert "| Сотрудник | Часы |" in content
        assert "**Итого**" in content
        # Per-user section with worklogs table.
        assert "| Ключ | Задача | Часы | Комментарий |" in content

    async def test_default_is_txt(self, tmp_path: Path) -> None:
        """Default format is txt (backward compatible)."""
        user_worklogs = {"alice": [_make_worklog("PROJECT-100", 3600, 15, "A")]}
        config = _make_config()
        mock_client = _make_mock_client(user_worklogs)

        result = await generate_team_report(
            cast(JiraTempoClient, mock_client),
            config,
            users=["alice"],
            date_from="2026-06-15",
            date_to="2026-06-19",
            output_dir=tmp_path,
        )

        assert result.file_path.suffix == ".txt"


class TestTeamReportJSON:
    """JSON format: .json extension, structured data."""

    async def test_json_format(self, tmp_path: Path) -> None:
        user_worklogs = {
            "alice": [_make_worklog("PROJECT-100", 3600, 15, "Alice on A")],
            "bob": [_make_worklog("PROJECT-200", 7200, 16, "Bob on B")],
        }
        config = _make_config()
        mock_client = _make_mock_client(
            user_worklogs, {"PROJECT-200": "Task B"}
        )

        result = await generate_team_report(
            cast(JiraTempoClient, mock_client),
            config,
            users=["alice", "bob"],
            date_from="2026-06-15",
            date_to="2026-06-19",
            output_dir=tmp_path,
            fmt="json",
        )

        assert result.file_path.suffix == ".json"
        import json as _json
        data = _json.loads(result.file_path.read_text(encoding="utf-8"))
        assert data["date_from"] == "2026-06-15"
        assert data["date_to"] == "2026-06-19"
        assert data["grand_total_seconds"] == 10800
        assert len(data["per_user"]) == 2
