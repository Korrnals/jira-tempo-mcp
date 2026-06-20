"""Report template system — Protocol, registry, and builtin templates.

A template is anything that implements the :class:`ReportTemplate` protocol.
Builtin templates live in :mod:`jira_tempo_mcp.templates.builtin`; custom
templates are discovered from ``REPORT_TEMPLATE_DIR`` (see loader.py).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from ..config import Config

logger = logging.getLogger(__name__)


class ReportTemplate(Protocol):
    """Contract for report templates.

    Implementations may be Python classes (opt-in via
    ``REPORT_TEMPLATE_ALLOW_PY``) or Jinja2 ``.j2`` files loaded into a
    sandboxed environment.
    """

    name: str
    description: str

    def render(
        self,
        worklogs: list[dict[str, Any]],
        config: Config,
        **kwargs: Any,
    ) -> str:
        """Render worklogs to report text."""
        ...


class TemplateRegistry:
    """Registry mapping template names to template instances.

    Builtin templates are registered at import time; custom templates are
    added by :func:`jira_tempo_mcp.templates.loader.discover_custom_templates`.
    """

    def __init__(self) -> None:
        self._templates: dict[str, ReportTemplate] = {}

    def register(self, template: ReportTemplate) -> None:
        """Register a template under its ``name``."""
        self._templates[template.name] = template
        logger.debug("Registered template %r", template.name)

    def get(self, name: str) -> ReportTemplate | None:
        """Return the template with ``name`` or ``None`` if not registered."""
        return self._templates.get(name)

    def all(self) -> list[ReportTemplate]:
        """Return all registered templates sorted by name."""
        return sorted(self._templates.values(), key=lambda t: t.name)

    def names(self) -> list[str]:
        """Return all registered template names sorted alphabetically."""
        return sorted(self._templates.keys())

    def __len__(self) -> int:
        return len(self._templates)

    def __contains__(self, name: str) -> bool:
        return name in self._templates


def builtin_registry() -> TemplateRegistry:
    """Build a registry populated with builtin templates only.

    Custom templates are added separately by the loader at server startup.
    """
    from .builtin.default import DefaultTemplate
    from .builtin.team_report import TeamReportTemplate
    from .builtin.weekly_summary import WeeklySummaryTemplate

    registry = TemplateRegistry()
    registry.register(DefaultTemplate())
    registry.register(WeeklySummaryTemplate())
    registry.register(TeamReportTemplate())
    return registry


__all__ = [
    "ReportTemplate",
    "TemplateRegistry",
    "builtin_registry",
]
