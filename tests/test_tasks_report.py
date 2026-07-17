"""Tests for tasks_report.py — individual and group reports, active filtering."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from jira_tempo_mcp.client import JiraTempoClient
from jira_tempo_mcp.config import Config
from jira_tempo_mcp.tasks_report import (
    TasksReportResult,
    _format_jira_date,
    _is_active_task,
    _status_emoji,
    generate_tasks_report,
)


def _make_config(**overrides: Any) -> Config:
    defaults: dict[str, Any] = {
        "jira_base_url": "https://jira.test.example",
        "jira_user": "testuser",
        "jira_pat": "fake-pat-for-testing",
        "author_display_name": "Тестовый Пользователь",
        "timezone": "Europe/Moscow",
    }
    defaults.update(overrides)
    return Config(**defaults)


_UNSET = object()  # sentinel for "not explicitly provided"


def _make_task(
    key: str,
    summary: str,
    status: str,
    status_category: str = "To Do",
    *,
    status_category_key: Any = _UNSET,
    duedate: str = "",
    priority: str = "Medium",
    comments: int = 0,
) -> dict[str, Any]:
    """Build a task dict matching list_user_tasks output shape."""
    # Default status_category_key based on status_category if not explicit.
    if status_category_key is _UNSET:
        key_map = {"In Progress": "indeterminate", "To Do": "new", "Done": "done"}
        status_category_key = key_map.get(status_category, "new")
    comment_list = [
        {"author": f"User{i}", "body": f"Comment {i}", "created": "2026-06-20T10:00:00.000+0300"}
        for i in range(comments)
    ]
    return {
        "key": key,
        "summary": summary,
        "status": status,
        "statusCategory": status_category,
        "statusCategoryKey": status_category_key,
        "duedate": duedate,
        "priority": priority,
        "issuetype": "Task",
        "project": "DEVOPS",
        "projectKey": "DEVOPS",
        "created": "2026-06-01T10:00:00.000+0300",
        "updated": "2026-06-20T10:00:00.000+0300",
        "comments": comment_list[-3:],
        "comment_count": comments,
    }


def _make_mock_client(
    user_tasks: dict[str, list[dict[str, Any]]],
    display_names: dict[str, str] | None = None,
) -> AsyncMock:
    """Mock client: list_user_tasks per user, search_users for display names."""
    mock = AsyncMock(spec=JiraTempoClient)

    async def _list_user_tasks(
        username: str,
        *,
        status_filter: list[str] | None = None,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        tasks = user_tasks.get(username, [])
        if status_filter:
            tasks = [t for t in tasks if t.get("status") in status_filter]
        return tasks[:max_results]

    async def _search_users(query: str, max_results: int = 10) -> list[dict[str, Any]]:
        names = display_names or {}
        if query in names:
            return [
                {
                    "name": query,
                    "key": f"JIRAUSER_{query}",
                    "displayName": names[query],
                    "emailAddress": "",
                    "active": True,
                }
            ]
        return []

    mock.list_user_tasks.side_effect = _list_user_tasks
    mock.search_users.side_effect = _search_users
    return mock


# --- _format_jira_date ---


class TestFormatJiraDate:
    def test_plain_date(self) -> None:
        assert _format_jira_date("2026-06-30") == "30.06.2026"

    def test_iso_datetime(self) -> None:
        assert _format_jira_date("2026-06-20T11:43:12.000+0300") == "20.06.2026"

    def test_empty(self) -> None:
        assert _format_jira_date("") == ""

    def test_invalid(self) -> None:
        # Invalid input returns the raw string (graceful fallback).
        assert _format_jira_date("not-a-date") == "not-a-date"


# --- _is_active_task ---


class TestIsActiveTask:
    def test_in_progress(self) -> None:
        task = _make_task("DEVOPS-1", "Test", "В работе", "In Progress")
        assert _is_active_task(task) is True

    def test_done(self) -> None:
        task = _make_task("DEVOPS-2", "Test", "Готово", "Done")
        assert _is_active_task(task) is False

    def test_to_do(self) -> None:
        task = _make_task("DEVOPS-3", "Test", "Открыта", "To Do")
        assert _is_active_task(task) is False

    def test_missing_category_key_fallback_ru(self) -> None:
        """Fallback to statusCategory name when key is empty (Russian)."""
        task = _make_task("DEVOPS-4", "Test", "В работе", "В работе", status_category_key="")
        assert _is_active_task(task) is True

    def test_missing_category_key_fallback_en(self) -> None:
        """Fallback to statusCategory name when key is empty (English)."""
        task = _make_task("DEVOPS-5", "Test", "In Progress", "In Progress", status_category_key="")
        assert _is_active_task(task) is True

    def test_missing_all_category(self) -> None:
        """No category info at all → not active."""
        task = _make_task("DEVOPS-6", "Test", "Unknown", "", status_category_key="")
        assert _is_active_task(task) is False


# --- generate_tasks_report: individual mode ---


class TestIndividualReport:
    async def test_single_user_all_tasks(self, tmp_path: Path) -> None:
        tasks = [
            _make_task(
                "DEVOPS-100", "Task A", "В работе", "In Progress", duedate="2026-06-30", comments=2
            ),
            _make_task("DEVOPS-101", "Task B", "Готово", "Done"),
            _make_task("DEVOPS-102", "Task C", "Открыта", "To Do"),
        ]
        config = _make_config()
        mock_client = _make_mock_client({"dmz": tasks}, {"dmz": "Зазнатнов Денис Михайлович"})

        result = await generate_tasks_report(
            cast(JiraTempoClient, mock_client),
            config,
            users=["dmz"],
            output_dir=tmp_path,
            fmt="txt",
        )

        assert isinstance(result, TasksReportResult)
        assert result.file_path.exists()
        assert result.total_tasks == 3

        content = result.file_path.read_text(encoding="utf-8")
        # Header with display name.
        assert "Зазнатнов Денис Михайлович" in content
        assert "(dmz)" in content
        # All statuses present.
        assert "В работе" in content
        assert "Готово" in content
        assert "Открыта" in content
        # Summary section.
        assert "Всего задач: 3" in content
        # Comments rendered.
        assert "Комментарии (2)" in content
        # File extension is .txt
        assert result.file_path.suffix == ".txt"

    async def test_single_user_active_only(self, tmp_path: Path) -> None:
        tasks = [
            _make_task("DEVOPS-100", "Active", "В работе", "In Progress"),
            _make_task("DEVOPS-101", "Done", "Готово", "Done"),
        ]
        config = _make_config()
        mock_client = _make_mock_client({"alice": tasks}, {"alice": "Alice"})

        result = await generate_tasks_report(
            cast(JiraTempoClient, mock_client),
            config,
            users=["alice"],
            active_only=True,
            output_dir=tmp_path,
            fmt="txt",
        )

        assert result.total_tasks == 1
        content = result.file_path.read_text(encoding="utf-8")
        assert "Active" in content
        assert "Done" not in content

    async def test_empty_tasks(self, tmp_path: Path) -> None:
        config = _make_config()
        mock_client = _make_mock_client({"nobody": []}, {"nobody": "Nobody"})

        result = await generate_tasks_report(
            cast(JiraTempoClient, mock_client),
            config,
            users=["nobody"],
            output_dir=tmp_path,
            fmt="txt",
        )

        assert result.total_tasks == 0
        content = result.file_path.read_text(encoding="utf-8")
        assert "Всего задач: 0" in content


# --- generate_tasks_report: group mode ---


class TestGroupReport:
    async def test_group_active_only(self, tmp_path: Path) -> None:
        user_tasks = {
            "golikhin": [
                _make_task("DEVOPS-1", "Active G1", "В работе", "In Progress"),
                _make_task("DEVOPS-2", "Done G1", "Готово", "Done"),
            ],
            "poperech": [
                _make_task("DEVOPS-3", "Active P1", "В работе", "In Progress"),
                _make_task("DEVOPS-4", "Active P2", "Открыта", "To Do"),
            ],
        }
        config = _make_config()
        mock_client = _make_mock_client(
            user_tasks,
            {"golikhin": "Голихин Леонид", "poperech": "Попереч Иван"},
        )

        result = await generate_tasks_report(
            cast(JiraTempoClient, mock_client),
            config,
            users=["golikhin", "poperech"],
            output_dir=tmp_path,
            fmt="txt",
        )

        # Group mode forces active_only — only In Progress tasks count.
        assert result.total_tasks == 2
        content = result.file_path.read_text(encoding="utf-8")
        assert "Отчёт по активным задачам команды" in content
        assert "Голихин Леонид" in content
        assert "Попереч Иван" in content
        # Done task should NOT appear.
        assert "Done G1" not in content
        # Active tasks present.
        assert "Active G1" in content
        assert "Active P1" in content
        # To Do task is NOT active (only In Progress category is).
        assert "Active P2" not in content
        # Summary.
        assert "Всего активных задач: 2" in content
        # File extension is .txt
        assert result.file_path.suffix == ".txt"

    async def test_group_user_with_no_active(self, tmp_path: Path) -> None:
        user_tasks = {
            "alice": [_make_task("DEVOPS-1", "Active", "В работе", "In Progress")],
            "bob": [_make_task("DEVOPS-2", "Done", "Готово", "Done")],
        }
        config = _make_config()
        mock_client = _make_mock_client(user_tasks, {"alice": "Alice", "bob": "Bob"})

        result = await generate_tasks_report(
            cast(JiraTempoClient, mock_client),
            config,
            users=["alice", "bob"],
            output_dir=tmp_path,
            fmt="txt",
        )

        assert result.total_tasks == 1
        content = result.file_path.read_text(encoding="utf-8")
        assert "(0 активных)" in content
        assert "Всего активных задач: 1" in content


# --- Validation ---


class TestValidation:
    async def test_empty_users_raises(self, tmp_path: Path) -> None:
        config = _make_config()
        mock_client = _make_mock_client({})

        with pytest.raises(ValueError, match="non-empty"):
            await generate_tasks_report(
                cast(JiraTempoClient, mock_client), config, users=[], output_dir=tmp_path
            )

    async def test_invalid_format_raises(self, tmp_path: Path) -> None:
        config = _make_config()
        mock_client = _make_mock_client({"alice": []}, {"alice": "Alice"})

        with pytest.raises(ValueError, match="Invalid format"):
            await generate_tasks_report(
                cast(JiraTempoClient, mock_client),
                config,
                users=["alice"],
                output_dir=tmp_path,
                fmt="xml",
            )


# --- Markdown format tests ---


class TestMarkdownIndividualReport:
    async def test_single_user_md_format(self, tmp_path: Path) -> None:
        tasks = [
            _make_task(
                "DEVOPS-100", "Task A", "В работе", "In Progress", duedate="2026-06-30", comments=2
            ),
            _make_task("DEVOPS-101", "Task B", "Готово", "Done"),
        ]
        config = _make_config()
        mock_client = _make_mock_client({"dmz": tasks}, {"dmz": "Зазнатнов Денис Михайлович"})

        result = await generate_tasks_report(
            cast(JiraTempoClient, mock_client),
            config,
            users=["dmz"],
            output_dir=tmp_path,
            fmt="md",
        )

        assert result.file_path.suffix == ".md"
        content = result.file_path.read_text(encoding="utf-8")
        # Markdown headers.
        assert content.startswith("# Отчёт по задачам:")
        assert "Зазнатнов Денис Михайлович" in content
        assert "(dmz)" in content
        assert "📅" in content
        # Table headers (right-aligned # column).
        assert "| Ключ |" in content
        assert "|---:|" in content
        # Collapsible comments.
        assert "<details>" in content
        assert "💬 Комментарии к DEVOPS-100" in content
        # Summary section.
        assert "## 📊 Резюме" in content
        assert "**Всего**" in content

    async def test_md_default_format(self, tmp_path: Path) -> None:
        """Default format is now md."""
        tasks = [_make_task("DEVOPS-1", "Test", "В работе", "In Progress")]
        config = _make_config()
        mock_client = _make_mock_client({"alice": tasks}, {"alice": "Alice"})

        result = await generate_tasks_report(
            cast(JiraTempoClient, mock_client),
            config,
            users=["alice"],
            output_dir=tmp_path,
        )

        assert result.file_path.suffix == ".md"
        content = result.file_path.read_text(encoding="utf-8")
        assert "# Отчёт по задачам:" in content


class TestMarkdownGroupReport:
    async def test_group_md_format(self, tmp_path: Path) -> None:
        user_tasks = {
            "golikhin": [
                _make_task("DEVOPS-1", "Active G1", "В работе", "In Progress"),
                _make_task("DEVOPS-2", "Done G1", "Готово", "Done"),
            ],
            "poperech": [
                _make_task("DEVOPS-3", "Active P1", "В работе", "In Progress"),
            ],
        }
        config = _make_config()
        mock_client = _make_mock_client(
            user_tasks,
            {"golikhin": "Голихин Леонид", "poperech": "Попереч Иван"},
        )

        result = await generate_tasks_report(
            cast(JiraTempoClient, mock_client),
            config,
            users=["golikhin", "poperech"],
            output_dir=tmp_path,
            fmt="md",
        )

        assert result.file_path.suffix == ".md"
        content = result.file_path.read_text(encoding="utf-8")
        assert "# Отчёт по активным задачам команды" in content
        assert "👥 Пользователи:" in content
        assert "## Голихин Леонид" in content
        assert "## Попереч Иван" in content
        assert "### 🔄" in content  # In Progress emoji
        assert "## 📊 Сводка" in content
        assert "**Всего**" in content
        # Done task should NOT appear.
        assert "Done G1" not in content


# --- JSON format tests ---


class TestJsonIndividualReport:
    async def test_single_user_json_format(self, tmp_path: Path) -> None:
        tasks = [
            _make_task("DEVOPS-100", "Task A", "В работе", "In Progress", comments=1),
            _make_task("DEVOPS-101", "Task B", "Готово", "Done"),
        ]
        config = _make_config()
        mock_client = _make_mock_client({"alice": tasks}, {"alice": "Alice"})

        result = await generate_tasks_report(
            cast(JiraTempoClient, mock_client),
            config,
            users=["alice"],
            output_dir=tmp_path,
            fmt="json",
        )

        assert result.file_path.suffix == ".json"
        import json as _json

        data = _json.loads(result.file_path.read_text(encoding="utf-8"))
        assert data["username"] == "alice"
        assert data["display_name"] == "Alice"
        assert data["total_tasks"] == 2
        assert len(data["status_groups"]) == 2

    async def test_group_json_format(self, tmp_path: Path) -> None:
        user_tasks = {
            "alice": [_make_task("DEVOPS-1", "Active", "В работе", "In Progress")],
            "bob": [_make_task("DEVOPS-2", "Done", "Готово", "Done")],
        }
        config = _make_config()
        mock_client = _make_mock_client(user_tasks, {"alice": "Alice", "bob": "Bob"})

        result = await generate_tasks_report(
            cast(JiraTempoClient, mock_client),
            config,
            users=["alice", "bob"],
            output_dir=tmp_path,
            fmt="json",
        )

        assert result.file_path.suffix == ".json"
        import json as _json

        data = _json.loads(result.file_path.read_text(encoding="utf-8"))
        assert data["total_active"] == 1  # Only alice has active tasks.
        assert len(data["per_user"]) == 2
        assert data["per_user"][0]["active_count"] == 1
        assert data["per_user"][1]["active_count"] == 0


# --- Emoji helper tests ---


class TestStatusEmoji:
    def test_in_progress(self) -> None:
        task = _make_task("DEVOPS-1", "Test", "В работе", "In Progress")
        assert _status_emoji(task) == "🔄"

    def test_done(self) -> None:
        task = _make_task("DEVOPS-2", "Test", "Готово", "Done")
        assert _status_emoji(task) == "✅"

    def test_to_do(self) -> None:
        task = _make_task("DEVOPS-3", "Test", "Открыта", "To Do")
        assert _status_emoji(task) == "📋"

    def test_fallback_no_category(self) -> None:
        task = _make_task("DEVOPS-4", "Test", "В работе", "В работе", status_category_key="")
        assert _status_emoji(task) == "🔄"


class TestTasksMdCommentSanitization:
    """Hotfix: multi-line / pipe-laden Jira comment bodies must not break MD."""

    def test_multiline_comment_body_stays_single_line(self) -> None:
        from jira_tempo_mcp.tasks_report import _render_individual_md

        task = {
            "key": "DEVOPS-100",
            "summary": "Task A",
            "status": "В работе",
            "statusCategory": "In Progress",
            "statusCategoryKey": "indeterminate",
            "duedate": "",
            "priority": "Medium",
            "updated": "2026-06-20T10:00:00.000+0300",
            "comments": [
                {
                    "author": "User1",
                    "body": "line one\nline two | with pipe",
                    "created": "2026-06-20T10:00:00.000+0300",
                }
            ],
            "comment_count": 1,
        }
        md = _render_individual_md("alice", "Alice", [task], "Europe/Moscow")
        # The comment must be rendered on a single list line (no raw newline
        # splitting it across two markdown items).
        comment_lines = [ln for ln in md.splitlines() if ln.startswith("- **User1**")]
        assert len(comment_lines) == 1
        line = comment_lines[0]
        assert "line one line two" in line  # newline collapsed to space
        assert "\\|" in line  # pipe escaped
