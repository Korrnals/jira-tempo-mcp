"""Template loader — discovers and loads builtin + custom templates.

Custom templates are discovered from ``Config.template_dir_resolved``:

* ``.j2`` files — loaded into a :class:`jinja2.sandbox.SandboxedEnvironment`
  (default, safe). The template name is the file stem.
* ``.py`` files — loaded via :mod:`importlib` only when
  ``REPORT_TEMPLATE_ALLOW_PY=1`` (opt-in, code execution risk). The module
  must expose a ``TEMPLATE`` attribute that implements
  :class:`jira_tempo_mcp.templates.ReportTemplate`.

Jinja2 is an optional dependency: if it is not installed, ``.j2`` templates
are skipped with a warning rather than crashing the server.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

from ..config import Config
from ..utils import format_seconds_to_human
from . import ReportTemplate, TemplateRegistry, builtin_registry
from ._shared import format_date

logger = logging.getLogger(__name__)

# Jinja2 is optional at runtime — import lazily so the server still starts
# if it is not installed (only .j2 templates become unavailable).
try:
    from jinja2 import Environment, FileSystemLoader, TemplateNotFound
    from jinja2.sandbox import SandboxedEnvironment

    _JINJA2_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without jinja2
    _JINJA2_AVAILABLE = False
    SandboxedEnvironment = None  # type: ignore[assignment, misc]
    Environment = None  # type: ignore[assignment, misc]
    FileSystemLoader = None  # type: ignore[assignment, misc]
    TemplateNotFound = None  # type: ignore[assignment, misc]


class JinjaTemplate:
    """Adapter wrapping a Jinja2 template as a :class:`ReportTemplate`."""

    # Provenance metadata surfaced by list_report_templates.
    kind: str = "custom"
    engine: str = "Jinja2"

    def __init__(self, name: str, description: str, env: Any, source_path: Path) -> None:
        self.name = name
        self.description = description
        self._env = env
        self._source_path = source_path

    def render(self, worklogs: list[dict[str, Any]], config: Config, **kwargs: Any) -> str:
        """Render the Jinja2 template with a sandboxed context."""
        template = self._env.get_template(self._source_path.name)
        context = {
            "worklogs": worklogs,
            "config": config,
            "format_seconds": format_seconds_to_human,
            "format_date": format_date,
            "users": kwargs.get("users", []),
            "summary": kwargs.get("summary", ""),
            "per_user_worklogs": kwargs.get("per_user_worklogs", {}),
            "issue_titles": kwargs.get("issue_titles", {}),
            "monday": kwargs.get("monday"),
            "friday": kwargs.get("friday"),
        }
        context.update({k: v for k, v in kwargs.items() if k not in context})
        result: str = template.render(**context)
        return result


class PythonTemplate:
    """Adapter wrapping a user-supplied Python module as a ReportTemplate."""

    # Provenance metadata surfaced by list_report_templates.
    kind: str = "custom"
    engine: str = "Python"

    def __init__(self, template: ReportTemplate, source_path: Path) -> None:
        self._template = template
        self._source_path = source_path
        self.name = getattr(template, "name", source_path.stem)
        self.description = getattr(template, "description", f"Python template {source_path.name}")

    def render(self, worklogs: list[dict[str, Any]], config: Config, **kwargs: Any) -> str:
        return self._template.render(worklogs, config, **kwargs)


def _load_python_template(path: Path) -> ReportTemplate | None:
    """Load a .py template module and extract its ``TEMPLATE`` attribute.

    Returns None and logs a warning if the module does not expose a valid
    ``TEMPLATE`` attribute.
    """
    module_name = f"jtm_template_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        logger.warning("Could not create module spec for %s", path)
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 — user code, broad catch is correct
        logger.warning("Python template %s failed to load: %s", path, exc)
        return None
    template = getattr(module, "TEMPLATE", None)
    if template is None:
        logger.warning("Python template %s has no TEMPLATE attribute — skipped", path)
        return None
    if not (hasattr(template, "render") and hasattr(template, "name")):
        logger.warning("Python template %s TEMPLATE does not satisfy ReportTemplate protocol", path)
        return None
    return PythonTemplate(template, path)


def _load_jinja_template(path: Path, env: Any) -> ReportTemplate | None:
    """Load a .j2 template into the sandboxed environment."""
    if not _JINJA2_AVAILABLE:
        logger.warning(
            "Jinja2 not installed — skipping .j2 template %s (pip install jinja2)",
            path,
        )
        return None
    try:
        # Pre-compile to validate syntax.
        env.get_template(path.name)
    except TemplateNotFound:
        logger.warning("Jinja2 template %s not found in env", path)
        return None
    except Exception as exc:  # noqa: BLE001 — jinja2 raises various errors
        logger.warning("Jinja2 template %s has syntax error: %s", path, exc)
        return None
    description = f"Jinja2 template {path.name}"
    return JinjaTemplate(path.stem, description, env, path)


def discover_custom_templates(config: Config) -> list[ReportTemplate]:
    """Scan the custom template directory and return loaded templates.

    Builtin templates are not included here — use :func:`build_registry`
    to get a full registry.
    """
    template_dir = Path(config.template_dir_resolved)
    if not template_dir.exists() or not template_dir.is_dir():
        logger.debug("Template dir %s does not exist — no custom templates", template_dir)
        return []

    env: Any = None
    if _JINJA2_AVAILABLE:
        env = SandboxedEnvironment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=False,  # reports are plain text, not HTML
            trim_blocks=True,
            lstrip_blocks=True,
        )

    templates: list[ReportTemplate] = []
    for path in sorted(template_dir.iterdir()):
        if path.is_dir() or path.name.startswith("_"):
            continue
        suffix = path.suffix.lower()
        if suffix == ".j2":
            tpl = _load_jinja_template(path, env)
            if tpl is not None:
                templates.append(tpl)
        elif suffix == ".py":
            if not config.report_template_allow_py:
                logger.warning(
                    "Python template %s skipped — set REPORT_TEMPLATE_ALLOW_PY=1 to enable",
                    path,
                )
                continue
            logger.warning("Loading Python template %s — ensure this file is trusted", path)
            tpl = _load_python_template(path)
            if tpl is not None:
                templates.append(tpl)
        else:
            logger.debug("Ignoring non-template file %s", path)
    return templates


def build_registry(config: Config) -> TemplateRegistry:
    """Build a full registry: builtin templates + custom discovered ones."""
    registry = builtin_registry()
    for tpl in discover_custom_templates(config):
        registry.register(tpl)
    return registry


def resolve_template(config: Config, registry: TemplateRegistry) -> ReportTemplate | None:
    """Resolve the active template for ``generate_weekly_report``.

    Priority:
      1. ``REPORT_TEMPLATE_PATH`` — explicit file path (loaded ad-hoc).
      2. ``REPORT_TEMPLATE`` — name looked up in the registry.
      3. Fallback to the ``default`` builtin.
    """
    if config.report_template_path:
        path = Path(config.report_template_path)
        if not path.exists():
            logger.warning("REPORT_TEMPLATE_PATH %s does not exist", path)
        else:
            suffix = path.suffix.lower()
            if suffix == ".j2":
                env: Any = None
                if _JINJA2_AVAILABLE:
                    env = SandboxedEnvironment(
                        loader=FileSystemLoader(str(path.parent)),
                        autoescape=False,
                        trim_blocks=True,
                        lstrip_blocks=True,
                    )
                tpl = _load_jinja_template(path, env)
                if tpl is not None:
                    return tpl
            elif suffix == ".py":
                if not config.report_template_allow_py:
                    logger.warning(
                        "REPORT_TEMPLATE_PATH points to .py but REPORT_TEMPLATE_ALLOW_PY=0"
                    )
                else:
                    tpl = _load_python_template(path)
                    if tpl is not None:
                        return tpl
            else:
                logger.warning("Unsupported template file extension: %s", path)

    name = config.report_template or "default"
    tpl = registry.get(name)
    if tpl is not None:
        return tpl
    logger.warning("Template %r not found — falling back to 'default'", name)
    return registry.get("default")


__all__ = [
    "JinjaTemplate",
    "PythonTemplate",
    "build_registry",
    "discover_custom_templates",
    "resolve_template",
]
