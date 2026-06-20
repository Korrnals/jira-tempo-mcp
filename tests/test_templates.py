"""Tests for the template system — registry, builtin, Jinja2, Python opt-in, sandbox."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from jira_tempo_mcp.config import Config
from jira_tempo_mcp.templates import ReportTemplate, TemplateRegistry, builtin_registry
from jira_tempo_mcp.templates.builtin.default import DefaultTemplate
from jira_tempo_mcp.templates.builtin.team_report import TeamReportTemplate
from jira_tempo_mcp.templates.builtin.weekly_summary import WeeklySummaryTemplate
from jira_tempo_mcp.templates.loader import (
    build_registry,
    discover_custom_templates,
    resolve_template,
)


def _make_config(**overrides: Any) -> Config:
    defaults: dict[str, Any] = {
        "jira_base_url": "https://jira.test.example",
        "jira_user": "testuser",
        "jira_pat": "fake-pat",
        "section_map": {"PROJECT-100": "Section A"},
        "stable_order": ["PROJECT-100"],
        "non_issue_sections": [],
    }
    defaults.update(overrides)
    return Config(**defaults)


def _make_worklog(key: str, seconds: int, day: int = 15, comment: str = "") -> dict[str, Any]:
    wl: dict[str, Any] = {
        "issueKey": key,
        "timeSpentSeconds": seconds,
        "startDate": f"2026-06-{day:02d}",
    }
    if comment:
        wl["comment"] = comment
    return wl


# --- Registry ---


class TestTemplateRegistry:
    """Registry register/get/list/contains."""

    def test_register_and_get(self) -> None:
        reg = TemplateRegistry()
        tpl = DefaultTemplate()
        reg.register(tpl)
        assert reg.get("default") is tpl
        assert "default" in reg
        assert len(reg) == 1

    def test_get_missing_returns_none(self) -> None:
        reg = TemplateRegistry()
        assert reg.get("nope") is None

    def test_names_sorted(self) -> None:
        reg = TemplateRegistry()
        reg.register(WeeklySummaryTemplate())
        reg.register(DefaultTemplate())
        reg.register(TeamReportTemplate())
        assert reg.names() == ["default", "team_report", "weekly_summary"]

    def test_all_sorted_by_name(self) -> None:
        reg = TemplateRegistry()
        reg.register(WeeklySummaryTemplate())
        reg.register(DefaultTemplate())
        templates = reg.all()
        assert [t.name for t in templates] == ["default", "weekly_summary"]


class TestBuiltinRegistry:
    """builtin_registry() has the 3 builtin templates."""

    def test_builtin_registry_has_three(self) -> None:
        reg = builtin_registry()
        assert set(reg.names()) == {"default", "weekly_summary", "team_report"}

    def test_builtin_default_renders(self) -> None:
        reg = builtin_registry()
        tpl = reg.get("default")
        assert tpl is not None
        config = _make_config()
        text = tpl.render(
            [_make_worklog("PROJECT-100", 3600, 15, "Stand support")],
            config,
            monday=date(2026, 6, 15),
            friday=date(2026, 6, 19),
            issue_titles={"PROJECT-100": "Section A"},
        )
        assert "Section A" in text
        assert "Stand support" in text

    def test_builtin_weekly_summary_renders(self) -> None:
        reg = builtin_registry()
        tpl = reg.get("weekly_summary")
        assert tpl is not None
        config = _make_config()
        text = tpl.render(
            [_make_worklog("PROJECT-100", 3600, 15), _make_worklog("PROJECT-200", 7200, 16)],
            config,
            monday=date(2026, 6, 15),
            friday=date(2026, 6, 19),
            issue_titles={"PROJECT-100": "Section A", "PROJECT-200": "Task B"},
        )
        assert "Сводка" in text
        assert "3h" in text  # 3600 + 7200 = 10800s = 3h
        assert "PROJECT-200" in text  # top issue

    def test_builtin_team_report_renders(self) -> None:
        reg = builtin_registry()
        tpl = reg.get("team_report")
        assert tpl is not None
        config = _make_config()
        text = tpl.render(
            [_make_worklog("PROJECT-100", 3600, 15)],
            config,
            monday=date(2026, 6, 15),
            friday=date(2026, 6, 19),
            issue_titles={"PROJECT-100": "Section A"},
            users=[("alice", "alice")],
            per_user_worklogs={"alice": [_make_worklog("PROJECT-100", 3600, 15)]},
        )
        assert "alice" in text
        assert "Сводка по команде" in text


# --- Custom Jinja2 templates ---


class TestJinja2Templates:
    """Jinja2 .j2 template discovery and rendering."""

    def test_jinja2_template_loaded(self, tmp_path: Path) -> None:
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "simple.j2").write_text(
            "Total: {{ worklogs | length }} worklogs\n"
            "Grand: {{ format_seconds(total) if total is defined else 'n/a' }}\n",
            encoding="utf-8",
        )
        config = _make_config(report_template_dir=str(template_dir))
        templates = discover_custom_templates(config)
        names = [t.name for t in templates]
        assert "simple" in names

    def test_jinja2_template_renders(self, tmp_path: Path) -> None:
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "count.j2").write_text("Count: {{ worklogs | length }}\n", encoding="utf-8")
        config = _make_config(report_template_dir=str(template_dir))
        registry = build_registry(config)
        tpl = registry.get("count")
        assert tpl is not None
        text = tpl.render([_make_worklog("PROJECT-100", 3600, 15)], config)
        assert "Count: 1" in text

    def test_jinja2_sandbox_blocks_unsafe(self, tmp_path: Path) -> None:
        """SandboxedEnvironment must block access to dunder attributes."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        # Unsafe construct — accessing __class__ to instantiate arbitrary objects.
        (template_dir / "unsafe.j2").write_text(
            "{{ config.__class__.__bases__ }}", encoding="utf-8"
        )
        config = _make_config(report_template_dir=str(template_dir))
        registry = build_registry(config)
        tpl = registry.get("unsafe")
        assert tpl is not None
        with pytest.raises(Exception):  # noqa: B017 — sandbox must raise
            tpl.render([], config)


# --- Custom Python templates (opt-in) ---


class TestPythonTemplates:
    """Python .py template loading requires REPORT_TEMPLATE_ALLOW_PY=1."""

    def test_python_template_refused_without_opt_in(self, tmp_path: Path) -> None:
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "mytpl.py").write_text(
            "class T:\n"
            "    name = 'mytpl'\n"
            "    description = 'test'\n"
            "    def render(self, worklogs, config, **kw):\n"
            "        return 'py template'\n"
            "TEMPLATE = T()\n",
            encoding="utf-8",
        )
        config = _make_config(
            report_template_dir=str(template_dir),
            report_template_allow_py=False,
        )
        templates = discover_custom_templates(config)
        assert all(t.name != "mytpl" for t in templates)

    def test_python_template_loaded_with_opt_in(self, tmp_path: Path) -> None:
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "mytpl.py").write_text(
            "class T:\n"
            "    name = 'mytpl'\n"
            "    description = 'test'\n"
            "    def render(self, worklogs, config, **kw):\n"
            "        return 'py template ok'\n"
            "TEMPLATE = T()\n",
            encoding="utf-8",
        )
        config = _make_config(
            report_template_dir=str(template_dir),
            report_template_allow_py=True,
        )
        registry = build_registry(config)
        tpl = registry.get("mytpl")
        assert tpl is not None
        assert tpl.render([], config) == "py template ok"

    def test_python_template_without_template_attr_skipped(self, tmp_path: Path) -> None:
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "notpl.py").write_text("x = 1\n", encoding="utf-8")
        config = _make_config(
            report_template_dir=str(template_dir),
            report_template_allow_py=True,
        )
        templates = discover_custom_templates(config)
        assert all(t.name != "notpl" for t in templates)


# --- resolve_template ---


class TestResolveTemplate:
    """resolve_template priority: path > name > default fallback."""

    def test_resolve_by_name(self, tmp_path: Path) -> None:
        config = _make_config(report_template="weekly_summary")
        registry = builtin_registry()
        tpl = resolve_template(config, registry)
        assert tpl is not None
        assert tpl.name == "weekly_summary"

    def test_resolve_falls_back_to_default(self, tmp_path: Path) -> None:
        config = _make_config(report_template="nonexistent")
        registry = builtin_registry()
        tpl = resolve_template(config, registry)
        assert tpl is not None
        assert tpl.name == "default"

    def test_resolve_explicit_path_j2(self, tmp_path: Path) -> None:
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        tpl_file = template_dir / "explicit.j2"
        tpl_file.write_text("Explicit: {{ worklogs | length }}\n", encoding="utf-8")
        config = _make_config(
            report_template_path=str(tpl_file),
            report_template_allow_py=False,
        )
        registry = builtin_registry()
        tpl = resolve_template(config, registry)
        assert tpl is not None
        text = tpl.render([_make_worklog("PROJECT-100", 3600, 15)], config)
        assert "Explicit: 1" in text


# --- Protocol conformance ---


class TestProtocolConformance:
    """Builtin templates satisfy the ReportTemplate protocol."""

    def test_default_satisfies_protocol(self) -> None:
        tpl: ReportTemplate = DefaultTemplate()  # type: ignore[assignment]
        assert tpl.name == "default"
        assert hasattr(tpl, "render")

    def test_weekly_summary_satisfies_protocol(self) -> None:
        tpl: ReportTemplate = WeeklySummaryTemplate()  # type: ignore[assignment]
        assert tpl.name == "weekly_summary"

    def test_team_report_satisfies_protocol(self) -> None:
        tpl: ReportTemplate = TeamReportTemplate()  # type: ignore[assignment]
        assert tpl.name == "team_report"
