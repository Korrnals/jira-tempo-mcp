"""Builtin report templates shipped with jira-tempo-mcp."""

from __future__ import annotations

from .default import DefaultTemplate
from .team_report import TeamReportTemplate
from .weekly_summary import WeeklySummaryTemplate

__all__ = [
    "DefaultTemplate",
    "TeamReportTemplate",
    "WeeklySummaryTemplate",
]
