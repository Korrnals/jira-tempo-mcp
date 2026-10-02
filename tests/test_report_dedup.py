"""Regression tests for duplicate worklog aggregation in reports (v0.6.1 fix).

Owner-reported defect: a weekly report rendered two blocks for DEVOPS-11025 —
«PROXY-BOT: Создать agent registry / agent-gateway» with 6h and, again, with
3h. Two real Tempo worklogs (same issue, same header comment, hours differ)
were rendered as separate blocks because the grouping key was the full
comment. The fix aggregates by the first comment line (header) and sums the
hours; true duplicate worklog ids (fetch/pagination defect) are dropped.

Three required regression shapes:
(a) two worklogs same issue + same header comment, different hours → ONE
    block with summed hours;
(b) true duplicate worklog ids → deduped at fetch level;
(c) worklogs with DIFFERENT header comments stay separate lines (aggregation
    must not over-merge), and byte-identical comments still group.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest

from jira_tempo_mcp.config import Config
from jira_tempo_mcp.report import generate_weekly_report
from jira_tempo_mcp.templates._shared import dedupe_worklogs_by_id, extract_worklog_id
from jira_tempo_mcp.templates.builtin.default import DefaultTemplate

MONDAY = date(2026, 9, 28)
FRIDAY = date(2026, 10, 2)


def _make_config() -> Config:
    return Config(
        jira_base_url="https://jira.test.example",
        jira_user="testuser",
        jira_pat="fake-pat-for-testing",
        report_author_header="golikhin",
    )


def _wl(
    key: str,
    seconds: int,
    comment: str,
    *,
    tempo_id: int | None = None,
    started: str = "2026-09-28",
) -> dict[str, Any]:
    wl: dict[str, Any] = {
        "issueKey": key,
        "timeSpentSeconds": seconds,
        "comment": comment,
        "started": started,
    }
    if tempo_id is not None:
        wl["tempoWorklogId"] = tempo_id
    return wl


# --- (a) same issue + same header comment, different hours → one block -------


class TestHeaderAggregation:
    """Aggregation by first comment line sums hours (owner-reported shape)."""

    def test_two_worklogs_same_header_different_hours_single_block(self) -> None:
        """(a) 6h + 3h with an identical header render as one 9h block."""
        header = "PROXY-BOT: Создать agent registry  / agent-gateway"
        worklogs = [
            _wl("DEVOPS-11025", 21600, f"{header}\n+ разработка платформы"),
            _wl(
                "DEVOPS-11025",
                10800,
                f"{header}\n+ разрабокта платформы",  # typo variant, as in artefact
            ),
        ]
        rendered = DefaultTemplate().render(
            worklogs,
            _make_config(),
            monday=MONDAY,
            friday=FRIDAY,
            issue_titles={"DEVOPS-11025": header},
        )
        # The header line appears exactly ONCE as a rendered '+' item.
        item_lines = [line for line in rendered.splitlines() if "+ PROXY-BOT:" in line]
        assert len(item_lines) == 1, rendered
        # Hours summed: 6h + 3h = 9h in the merged block.
        assert "9h" in rendered
        # The second block is gone — no second 6h/3h pair.
        assert "6h" not in rendered
        assert "3h" not in rendered

    def test_same_header_byte_identical_comments_aggregate(self) -> None:
        """Byte-identical comments always merged (pre-existing behaviour kept)."""
        comment = "Обсуждение архитектуры\n+ правки по итогам"
        worklogs = [
            _wl("DEVOPS-100", 3600, comment),
            _wl("DEVOPS-100", 7200, comment),
        ]
        rendered = DefaultTemplate().render(
            worklogs,
            _make_config(),
            monday=MONDAY,
            friday=FRIDAY,
            issue_titles={"DEVOPS-100": "T"},
        )
        assert "+ правки по итогам — 3h" in rendered
        assert rendered.count("+ Обсуждение архитектуры") == 1

    # --- (c) over-merge guards ------------------------------------------------

    def test_different_headers_stay_separate(self) -> None:
        """(c) distinct header rows must NOT be merged by the fix."""
        worklogs = [
            _wl("DEVOPS-100", 3600, "Анализ логов\n+ поиск аномалий"),
            _wl("DEVOPS-100", 7200, "Аудит компонентов\n+ проверка конфигураций"),
        ]
        rendered = DefaultTemplate().render(
            worklogs,
            _make_config(),
            monday=MONDAY,
            friday=FRIDAY,
            issue_titles={"DEVOPS-100": "T"},
        )
        # Multi-line comments attach the time suffix to the LAST body line.
        assert "+ Анализ логов\n\t+ поиск аномалий — 1h" in rendered
        assert "+ Аудит компонентов\n\t+ проверка конфигураций — 2h" in rendered

    def test_worklogs_on_different_days_same_header_aggregate(self) -> None:
        """(c/period semantics) report renders per-period lines without days —
        same header on different days is one logical row, hours summed."""
        header = "Сопровождение стендов"
        worklogs = [
            _wl("DEVOPS-101", 21600, header, started="2026-09-28"),
            _wl("DEVOPS-101", 3600, header, started="2026-09-29"),
        ]
        rendered = DefaultTemplate().render(
            worklogs,
            _make_config(),
            monday=MONDAY,
            friday=FRIDAY,
            issue_titles={"DEVOPS-101": header},
        )
        assert rendered.count(f"+ {header} — 7h") == 1


# --- (b) true duplicate worklog ids → deduped --------------------------------


class TestFetchLevelDedup:
    """Repeating Tempo ids are a fetch defect — drop, keep first, log ids."""

    def test_duplicate_ids_dropped_first_wins(self) -> None:
        worklogs = [
            _wl("DEVOPS-1", 3600, "a", tempo_id=10),
            _wl("DEVOPS-1", 3600, "a", tempo_id=10),  # same id — dup
            _wl("DEVOPS-1", 7200, "b", tempo_id=11),
        ]
        kept, dupes = dedupe_worklogs_by_id(worklogs)
        assert len(kept) == 2
        assert dupes == ["10"]
        # First occurrence wins: the 7200 'b' entry is intact.
        assert extract_worklog_id(kept[1]) == "11"

    def test_idless_worklogs_never_dropped(self) -> None:
        worklogs = [
            _wl("DEVOPS-1", 3600, "a"),
            _wl("DEVOPS-1", 3600, "a"),  # no ids — cannot prove duplicity
        ]
        kept, dupes = dedupe_worklogs_by_id(worklogs)
        assert len(kept) == 2
        assert dupes == []

    def test_extract_worklog_id_variants(self) -> None:
        assert extract_worklog_id({"tempoWorklogId": 42}) == "42"
        assert extract_worklog_id({"id": "77"}) == "77"
        assert extract_worklog_id({"worklogId": "5"}) == "5"
        assert extract_worklog_id({"comment": "x"}) is None
        assert extract_worklog_id({}) is None

    @pytest.mark.asyncio
    async def test_weekly_generator_dedupes_by_id(self, tmp_path: Any) -> None:
        """End-to-end: the weekly generator drops a repeated worklog id."""
        from unittest.mock import AsyncMock

        from jira_tempo_mcp.client import JiraTempoClient

        worklogs = [
            _wl("DEVOPS-1", 3600, "row", tempo_id=10),
            _wl("DEVOPS-1", 3600, "row", tempo_id=10),  # same id — dup
        ]
        mock = AsyncMock(spec=JiraTempoClient)
        mock.find_worker_key.return_value = "worker123"
        mock.search_worklogs.return_value = worklogs

        path = await generate_weekly_report(
            cast("Any", mock),
            _make_config(),
            target_date=MONDAY,
            output_dir=tmp_path,
        )
        report = Path(path).read_text(encoding="utf-8")
        assert "+ row — 1h" in report  # NOT 2h: the dup was dropped
        assert "+ row — 2h" not in report


# --- Artefact replication: DEVOPS-11025 real-world shape ----------------------


class TestArtefactReplication:
    """The owner artefact case, rendered through the real default template."""

    ARTEFACT_HEADER = "PROXY-BOT: Создать agent registry  / agent-gateway"

    def _render(self) -> str:
        worklogs = [
            _wl(
                "DEVOPS-11025",
                21600,
                f"{self.ARTEFACT_HEADER}\n+ разработка платформы",
            ),
            _wl(
                "DEVOPS-11025",
                10800,
                f"{self.ARTEFACT_HEADER}\n+ разрабокта платформы",
            ),
        ]
        cfg = Config(
            jira_base_url="https://jira.test.example",
            jira_user="testuser",
            jira_pat="fake-pat-for-testing",
            report_author_header="golikhin",
        )
        return DefaultTemplate().render(
            worklogs,
            cfg,
            monday=MONDAY,
            friday=FRIDAY,
            issue_titles={"DEVOPS-11025": self.ARTEFACT_HEADER},
        )

    def test_header_rendered_once(self) -> None:
        out = self._render()
        assert out.count("+ PROXY-BOT: Создать agent registry") == 1

    def test_hours_summed_9h(self) -> None:
        out = self._render()
        assert "— 9h" in out

    def test_body_lines_preserved(self) -> None:
        out = self._render()
        assert "разработка платформы" in out
        assert "разрабокта платформы" in out  # typo variant kept, not dropped
