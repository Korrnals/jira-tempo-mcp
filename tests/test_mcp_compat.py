"""Drift guard for the ``mcp`` SDK API surface ``server.py`` relies on.

The server is built on the low-level ``Server`` decorators (``list_tools``,
``call_tool``). mcp 2.x removed them — a fresh ``pip install jira-tempo-mcp``
resolving mcp 2.x crashed at startup with an ``AttributeError`` in
``serve()``. The dependency is therefore pinned ``mcp>=1.0.0,<2`` in
``pyproject.toml``; these tests fail loudly if the pin is ever dropped or
the decorators disappear within the pinned range.
"""

from __future__ import annotations

from importlib.metadata import version


def test_lowlevel_server_still_has_decorators() -> None:
    """``Server.list_tools`` / ``Server.call_tool`` must exist (mcp 1.x API)."""
    from mcp.server.lowlevel import Server

    assert hasattr(Server, "list_tools")
    assert hasattr(Server, "call_tool")


def test_server_module_imports_on_pinned_mcp() -> None:
    """``jira_tempo_mcp.server`` imports cleanly and mcp resolves inside <2."""
    import jira_tempo_mcp.server  # noqa: F401 — import is the assertion

    assert int(version("mcp").split(".")[0]) < 2
