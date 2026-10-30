"""P7 (backlog wave 2026-10-30): create_worklogs — batch worklog creation.

Contract:
- entries: array of {issue_key, time_spent, comment?, date_started?}, cap 20;
- ALL entries validated BEFORE the first write — invalid input writes
  nothing AND makes no network call at all (worker-key lookup included);
- sequential writes, NO auto-retries (non-idempotent POST);
- per-entry ok(id) / error(reason); one failure does not stop the rest;
- human-readable summary with written/failed counts.

Offline: fully mocked client, no HTTP, no .env reads.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
import pytz

from jira_tempo_mcp.client import JiraTempoClient, JiraTempoError
from jira_tempo_mcp.config import Config
from jira_tempo_mcp.server import TOOLS, _handle_create_worklogs
from jira_tempo_mcp.worklog_batch import MAX_BATCH_ENTRIES, validate_batch_entries

TZ = "Europe/Moscow"


def _make_config(**overrides: Any) -> Config:
    defaults: dict[str, Any] = {
        "jira_base_url": "https://jira.test.example",
        "jira_user": "testuser",
        "jira_pat": "fake-pat-for-testing",
        "timezone": TZ,
    }
    defaults.update(overrides)
    return Config(**defaults)


def _entry(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "issue_key": "PROJECT-100",
        "time_spent": "1h 30m",
        "comment": "batch entry",
        "date_started": "2026-10-29",
    }
    entry.update(overrides)
    return entry


def _mock_client(
    created_ids: list[str] | None = None,
    fail_on_indices: set[int] | None = None,
) -> AsyncMock:
    """Mock client; fail_on_indices uses 1-based entry positions."""
    mock = AsyncMock(spec=JiraTempoClient)
    mock.find_worker_key.return_value = "wk-testuser"

    ids = created_ids or ["101", "102", "103"]
    failures = fail_on_indices or set()
    counter = {"n": 0}

    async def _create(**_kwargs: Any) -> dict[str, Any]:
        counter["n"] += 1
        if counter["n"] in failures:
            raise JiraTempoError("VALIDATION_FAILED: simulated Tempo rejection")
        return {"tempoWorklogId": ids[counter["n"] - 1]}

    mock.create_worklog.side_effect = _create
    return mock


# --- Happy path ---------------------------------------------------------------


class TestP7HappyPath:
    async def test_sequential_writes_with_ids_and_summary(self) -> None:
        config = _make_config()
        mock = _mock_client(created_ids=["201", "202"])
        result = await _handle_create_worklogs(
            {"entries": [_entry(), _entry(issue_key="PROJECT-101", time_spent="45m")]},
            config,
            cast(JiraTempoClient, mock),
        )
        assert mock.create_worklog.await_count == 2
        # Sequential: first call got the first entry.
        first_kwargs = mock.create_worklog.await_args_list[0].kwargs
        assert first_kwargs["issue_key"] == "PROJECT-100"
        assert first_kwargs["time_spent_seconds"] == 5400
        assert first_kwargs["date_started"] == "2026-10-29"
        assert first_kwargs["comment"] == "batch entry"
        assert first_kwargs["author_account_id"] == "wk-testuser"
        # Human-readable per-entry results + summary.
        assert "Batch result: 2 recorded, 0 failed (of 2 entries)." in result
        assert "- [1] OK PROJECT-100 — 1h 30m on 2026-10-29 — Worklog ID: 201" in result
        assert "- [2] OK PROJECT-101 — 45m on 2026-10-29 — Worklog ID: 202" in result

    async def test_datetime_date_started_normalized_to_date(self) -> None:
        config = _make_config()
        mock = _mock_client(created_ids=["301"])
        await _handle_create_worklogs(
            {"entries": [_entry(date_started="2026-10-29T14:30:00+0300")]},
            config,
            cast(JiraTempoClient, mock),
        )
        assert mock.create_worklog.await_args.kwargs["date_started"] == "2026-10-29"

    async def test_default_date_started_is_today_in_config_tz(self) -> None:
        config = _make_config()
        mock = _mock_client(created_ids=["401"])
        await _handle_create_worklogs(
            {"entries": [_entry(date_started=None)]},
            config,
            cast(JiraTempoClient, mock),
        )
        expected = datetime.now(pytz.timezone(TZ)).date().isoformat()
        assert mock.create_worklog.await_args.kwargs["date_started"] == expected


# --- All-or-nothing validation gate -------------------------------------------


class TestP7ValidationGate:
    async def test_invalid_key_writes_nothing_and_calls_no_network(self) -> None:
        config = _make_config()
        mock = _mock_client()
        with pytest.raises(ValueError, match="nothing was written"):
            await _handle_create_worklogs(
                {"entries": [_entry(), _entry(issue_key="not-a-key")]},
                config,
                cast(JiraTempoClient, mock),
            )
        # ZERO network activity: neither the worker lookup nor any write.
        mock.find_worker_key.assert_not_awaited()
        mock.create_worklog.assert_not_awaited()

    async def test_all_problems_reported_at_once(self) -> None:
        entries = [
            _entry(issue_key="BAD"),
            _entry(time_spent="banana"),
            _entry(date_started="31-12-2026"),
            _entry(comment=123),
        ]
        with pytest.raises(ValueError) as excinfo:
            validate_batch_entries(entries, timezone=TZ)
        message = str(excinfo.value)
        assert "entries[1]" in message and "Invalid issue key" in message
        assert "entries[2]" in message and "invalid time_spent" in message
        assert "entries[3]" in message and "Invalid date_started" in message
        assert "entries[4]" in message and "'comment' must be a string" in message

    async def test_over_cap_rejected_without_writes(self) -> None:
        config = _make_config()
        mock = _mock_client()
        entries = [_entry(issue_key=f"PROJECT-{100 + i}") for i in range(MAX_BATCH_ENTRIES + 1)]
        with pytest.raises(ValueError, match="Too many entries: 21 > 20"):
            await _handle_create_worklogs({"entries": entries}, config, cast(JiraTempoClient, mock))
        mock.find_worker_key.assert_not_awaited()
        mock.create_worklog.assert_not_awaited()

    async def test_empty_batch_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            validate_batch_entries([], timezone=TZ)

    async def test_non_list_entries_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be an array"):
            validate_batch_entries({"issue_key": "PROJECT-100"}, timezone=TZ)

    async def test_zero_duration_rejected(self) -> None:
        # "0h" parses to 0 seconds — must be rejected, not recorded.
        with pytest.raises(ValueError, match="greater than zero"):
            validate_batch_entries([_entry(time_spent="0h")], timezone=TZ)

    async def test_schema_declares_cap(self) -> None:
        tool = next(t for t in TOOLS if t.name == "create_worklogs")
        entries_schema = tool.inputSchema["properties"]["entries"]
        assert entries_schema["maxItems"] == 20
        assert entries_schema["minItems"] == 1
        assert tool.inputSchema["required"] == ["entries"]


# --- Per-entry failure semantics ----------------------------------------------


class TestP7PerEntryFailure:
    async def test_one_failure_continues_the_rest(self) -> None:
        config = _make_config()
        mock = _mock_client(created_ids=["501", "502", "503"], fail_on_indices={2})
        result = await _handle_create_worklogs(
            {
                "entries": [
                    _entry(issue_key="PROJECT-100"),
                    _entry(issue_key="PROJECT-101"),
                    _entry(issue_key="PROJECT-102"),
                ]
            },
            config,
            cast(JiraTempoClient, mock),
        )
        # Exactly len(entries) write attempts — NO retries.
        assert mock.create_worklog.await_count == 3
        assert "Batch result: 2 recorded, 1 failed (of 3 entries)." in result
        assert "- [1] OK PROJECT-100 — 1h 30m on 2026-10-29 — Worklog ID: 501" in result
        assert "- [2] FAILED PROJECT-101" in result
        assert "Jira/Tempo API error" in result
        assert "- [3] OK PROJECT-102 — 1h 30m on 2026-10-29 — Worklog ID: 503" in result

    async def test_all_failed_still_reports_each(self) -> None:
        config = _make_config()
        mock = _mock_client(created_ids=[], fail_on_indices={1, 2})
        result = await _handle_create_worklogs(
            {"entries": [_entry(), _entry(issue_key="PROJECT-101")]},
            config,
            cast(JiraTempoClient, mock),
        )
        assert "Batch result: 0 recorded, 2 failed (of 2 entries)." in result
        # "] FAILED" (not bare "FAILED" — the error text itself contains
        # "VALIDATION_FAILED").
        assert result.count("] FAILED") == 2
