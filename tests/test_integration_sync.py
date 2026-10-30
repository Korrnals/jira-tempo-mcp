"""Guard test: packaged integration docs must be byte-identical to their source.

The ``jira_tempo_mcp.integration`` package data (agent doc + skill +
knowledge doc) is read from the installed wheel by ``install-specialist``
(via ``importlib.resources``). The source of truth lives in
``copilot-integration/``; the copies under ``src/jira_tempo_mcp/integration/``
are build artefacts kept in sync by ``make sync-integration`` (which runs as
the first step of ``make build``).

Incident: the 0.8.0 wheel shipped 0.6.x-era copies — the repo docs carried
every 0.7.0/0.8.0 fix while the wheel installed stale instructions to
agents. This test fails the CI gate if the copies ever drift again.

Skipped when ``copilot-integration/`` is absent (e.g. a build context
without the dev-only source files).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_DIR = _REPO_ROOT / "copilot-integration"
_PACKAGE_DIR = _REPO_ROOT / "src" / "jira_tempo_mcp" / "integration"

# The three artefacts install-specialist loads from package data
# (specialist.py: AGENT_FILE_NAME, SKILL_SOURCE_NAME, KNOWLEDGE_DOC_NAME).
SYNCED_FILES = (
    "JTM_AGENT.md",
    "jira-tempo-reports.skill.md",
    "jtm-jira-tempo-reports.agent.md",
)


def test_packaged_integration_docs_match_source() -> None:
    missing_sources = [n for n in SYNCED_FILES if not (_SOURCE_DIR / n).is_file()]
    if missing_sources:
        pytest.skip(
            "copilot-integration source files absent (build context without "
            f"dev files): {', '.join(missing_sources)}"
        )

    for name in SYNCED_FILES:
        packaged = _PACKAGE_DIR / name
        source = _SOURCE_DIR / name
        assert packaged.is_file(), (
            f"packaged integration doc {name!r} is missing from "
            f"{_PACKAGE_DIR} — run 'make sync-integration'"
        )
        assert packaged.read_bytes() == source.read_bytes(), (
            f"packaged integration doc {name!r} has drifted from the source "
            f"of truth copilot-integration/{name} — run 'make sync-integration' "
            "before building (0.8.0 shipped stale 0.6.x-era docs this way)"
        )
