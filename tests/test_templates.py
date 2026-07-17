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


# --- Bullet/comment rendering helpers (hotfix: no double markers, splitting) ---


class TestBulletHelpers:
    """Unit tests for the shared bullet-rendering helpers."""

    def test_strip_bullet_marker_variants(self) -> None:
        from jira_tempo_mcp.templates._shared import strip_bullet_marker

        assert strip_bullet_marker("+ text") == "text"
        assert strip_bullet_marker("- text") == "text"
        assert strip_bullet_marker("* text") == "text"
        assert strip_bullet_marker("\u2022 text") == "text"
        assert strip_bullet_marker("\u2013 text") == "text"
        assert strip_bullet_marker("\u2014 text") == "text"
        assert strip_bullet_marker("1. text") == "text"
        assert strip_bullet_marker("2) text") == "text"
        assert strip_bullet_marker("\t+ text") == "text"

    def test_strip_bullet_marker_collapses_double(self) -> None:
        from jira_tempo_mcp.templates._shared import strip_bullet_marker

        # A doubly-marked source line collapses to a single clean string.
        assert strip_bullet_marker("+ + text") == "text"
        assert strip_bullet_marker("- + text") == "text"

    def test_strip_bullet_marker_keeps_hyphenated_words(self) -> None:
        from jira_tempo_mcp.templates._shared import strip_bullet_marker

        # No space after '-': it's part of a word, not a marker.
        assert strip_bullet_marker("re-deploy service") == "re-deploy service"
        assert strip_bullet_marker("text without marker") == "text without marker"

    def test_split_comment_lines_multiline(self) -> None:
        from jira_tempo_mcp.templates._shared import split_comment_lines

        comment = "+ разработка Helm-чарта\n+ корректировка чартов\n+ деплой"
        assert split_comment_lines(comment) == [
            "разработка Helm-чарта",
            "корректировка чартов",
            "деплой",
        ]

    def test_split_comment_lines_single(self) -> None:
        from jira_tempo_mcp.templates._shared import split_comment_lines

        assert split_comment_lines("just one action") == ["just one action"]

    def test_split_comment_lines_empty(self) -> None:
        from jira_tempo_mcp.templates._shared import split_comment_lines

        assert split_comment_lines("") == []
        assert split_comment_lines(None) == []
        assert split_comment_lines("\n\n  \n") == []

    def test_split_comment_lines_crlf(self) -> None:
        from jira_tempo_mcp.templates._shared import split_comment_lines

        assert split_comment_lines("a\r\nb\rc") == ["a", "b", "c"]

    def test_render_comment_lines_time_on_last_only(self) -> None:
        from jira_tempo_mcp.templates._shared import render_comment_lines

        out = render_comment_lines("+ a\n+ b\n+ c", indent="\t", marker="+", time_human="4h")
        assert out == ["\t+ a", "\t+ b", "\t+ c \u2014 4h"]

    def test_render_comment_lines_single(self) -> None:
        from jira_tempo_mcp.templates._shared import render_comment_lines

        out = render_comment_lines("only one", indent="\t", marker="+", time_human="2h")
        assert out == ["\t+ only one \u2014 2h"]

    def test_render_comment_lines_no_double_marker(self) -> None:
        from jira_tempo_mcp.templates._shared import render_comment_lines

        # Source already has '+' markers — must NOT become '+ +'.
        out = render_comment_lines("+ a\n+ b", indent="\t", marker="+", time_human=None)
        assert out == ["\t+ a", "\t+ b"]
        assert all("+ +" not in line for line in out)

    def test_render_comment_lines_empty(self) -> None:
        from jira_tempo_mcp.templates._shared import render_comment_lines

        assert render_comment_lines("", indent="\t", marker="+", time_human="1h") == []

    def test_render_comment_cell_single(self) -> None:
        from jira_tempo_mcp.templates._shared import render_comment_cell

        assert render_comment_cell("+ just one") == "just one"

    def test_render_comment_cell_multiline_uses_br(self) -> None:
        from jira_tempo_mcp.templates._shared import render_comment_cell

        cell = render_comment_cell("+ a\n+ b")
        assert "<br>" in cell
        assert "\n" not in cell  # no raw newline that would break the table
        assert cell == "\u2022 a<br>\u2022 b"

    def test_render_comment_cell_escapes_pipes(self) -> None:
        from jira_tempo_mcp.templates._shared import render_comment_cell

        cell = render_comment_cell("a | b\nc | d")
        assert "\\|" in cell
        assert "<br>" in cell

    def test_render_comment_cell_empty(self) -> None:
        from jira_tempo_mcp.templates._shared import render_comment_cell

        assert render_comment_cell("") == "\u2014"

    def test_group_raw_preserves_structure_and_sums(self) -> None:
        from jira_tempo_mcp.templates._shared import group_worklogs_by_comment_raw

        multiline = "+ разработка\n+ корректировка"
        worklogs = [
            {"timeSpentSeconds": 3600, "comment": multiline},
            {"timeSpentSeconds": 7200, "comment": multiline},
        ]
        grouped = group_worklogs_by_comment_raw(worklogs)
        # Two worklogs with the same (multi-line) comment group + sum.
        assert len(grouped) == 1
        comment, secs = grouped[0]
        assert secs == 10800
        # Raw newline structure preserved (not flattened).
        assert "\n" in comment

    def test_group_raw_matches_normalized_grouping_totals(self) -> None:
        from jira_tempo_mcp.templates._shared import (
            group_worklogs_by_comment,
            group_worklogs_by_comment_raw,
        )

        # Same comment up to whitespace differences must still group together.
        worklogs = [
            {"timeSpentSeconds": 1800, "comment": "+ a\n+ b"},
            {"timeSpentSeconds": 1800, "comment": "+ a   \n  + b"},
        ]
        norm = group_worklogs_by_comment(worklogs)
        raw = group_worklogs_by_comment_raw(worklogs)
        assert len(norm) == 1
        assert len(raw) == 1
        assert norm[0][1] == raw[0][1] == 3600


class TestDefaultTemplateMultilineComments:
    """Regression: multi-line worklog comments must not double-mark or merge."""

    def test_multiline_comment_splits_into_items(self) -> None:
        reg = builtin_registry()
        tpl = reg.get("default")
        assert tpl is not None
        config = _make_config()
        multiline = "+ разработка Helm-чарта\n+ корректировка чартов\n+ деплой"
        text = tpl.render(
            [_make_worklog("PROJECT-100", 14400, 15, multiline)],
            config,
            monday=date(2026, 6, 15),
            friday=date(2026, 6, 19),
            issue_titles={"PROJECT-100": "Section A"},
        )
        # (a) no double markers anywhere.
        assert "+ +" not in text
        # (b) each action is its own line with a single marker.
        assert "\t+ разработка Helm-чарта" in text
        assert "\t+ корректировка чартов" in text
        assert "\t+ деплой" in text
        # (c) the time suffix lands on the LAST sub-item only, exactly once.
        assert text.count("\u2014 4h") == 1
        assert "\t+ деплой \u2014 4h" in text

    def test_marker_unified_strips_dash_source(self) -> None:
        reg = builtin_registry()
        tpl = reg.get("default")
        assert tpl is not None
        config = _make_config()
        # Source mixes '-' and '+' markers — output must unify to '+'.
        mixed = "- first action\n* second action"
        text = tpl.render(
            [_make_worklog("PROJECT-100", 3600, 15, mixed)],
            config,
            monday=date(2026, 6, 15),
            friday=date(2026, 6, 19),
            issue_titles={"PROJECT-100": "Section A"},
        )
        assert "\t+ first action" in text
        assert "\t+ second action" in text
        # No stray source markers leaked into the rendered bullet text.
        assert "\t- first action" not in text
        assert "\t+ - first action" not in text


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
