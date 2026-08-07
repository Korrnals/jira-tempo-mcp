"""Security-focused tests (finding #26 — v0.4.1 full code review).

Covers the security-critical surfaces that a regression on would be
high-impact:

- output_dir path-traversal rejection  (_validate_output_dir)
- Jinja2 sandbox blocking dunder/globals escape  (SandboxedEnvironment)
- HTTP 5xx surfacing as JiraTempoError + retry-then-succeed on idempotent GET
- httpx.RequestError (network) surfacing as JiraTempoError + retry on GET
- .py template code-execution warning logged when REPORT_TEMPLATE_ALLOW_PY=1

These tests mock the httpx transport (httpx.MockTransport) so the client's
REAL retry loop is exercised — no real network, no credentials.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
import pytest

from jira_tempo_mcp.client import JiraTempoClient, JiraTempoError
from jira_tempo_mcp.config import Config
from jira_tempo_mcp.server import _validate_output_dir


def _make_config(**overrides: Any) -> Config:
    """Build a Config with sane test defaults; ``overrides`` override fields."""
    return Config(
        jira_base_url="https://jira.test.example",
        jira_user="testuser",
        jira_pat="fake-pat-for-testing",
        timezone="Europe/Moscow",
        **overrides,
    )


def _client_with_transport(handler, **config_overrides: Any) -> JiraTempoClient:
    """Build a real JiraTempoClient whose httpx calls route to ``handler``.

    ``handler`` is a callable(request: httpx.Request) -> httpx.Response.
    """
    client = JiraTempoClient(_make_config(**config_overrides))
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        timeout=30.0,
        verify=True,
        follow_redirects=False,
    )
    return client


# --- output_dir path-traversal rejection -------------------------------------


def test_output_dir_traversal_rejected(tmp_path: Path) -> None:
    """``output_dir`` resolving outside the allowed root must be rejected.

    A traversal payload like ``../../etc`` must raise ValueError, never
    return a Path — otherwise an attacker controlling the output_dir
    argument could write reports to arbitrary locations.
    """
    allowed_root = tmp_path / "reports"
    allowed_root.mkdir()
    config = _make_config(report_output_dir=str(allowed_root))

    # ``../../etc`` resolves far above the allowed root.
    traversal = str(tmp_path.parent / "etc")
    with pytest.raises(ValueError, match="outside the allowed root"):
        _validate_output_dir(traversal, config)

    # A path inside the root is accepted.
    inside = allowed_root / "sub"
    inside.mkdir()
    resolved = _validate_output_dir(str(inside), config)
    assert resolved == inside.resolve()


# --- Jinja2 sandbox blocks dunder / globals escape ---------------------------


def test_jinja_sandbox_blocks_dunder() -> None:
    """A Jinja2 template reaching for dunders/globals must be blocked.

    ``{{ ''.__class__.__init__.__globals__ }}`` is a classic sandbox-escape
    payload. SandboxedEnvironment must refuse attribute access to dunder
    members, raising SecurityError (not rendering the globals dict).
    """
    jinja2 = pytest.importorskip("jinja2")
    from jinja2.sandbox import SandboxedEnvironment

    env = SandboxedEnvironment(autoescape=False)
    payload = "{{ ''.__class__.__init__.__globals__ }}"

    with pytest.raises(jinja2.exceptions.SecurityError):
        env.from_string(payload).render()


# --- HTTP 5xx raises JiraTempoError + retry-then-succeed on idempotent GET ---


@pytest.mark.asyncio
async def test_request_5xx_raises_when_no_retry() -> None:
    """With http_max_retries=0 (default), a 503 must raise immediately.

    This is the backwards-compatible baseline: a single 5xx surfaces as a
    JiraTempoError carrying the status code.
    """
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={"error": "service unavailable"})

    client = _client_with_transport(handler, http_max_retries=0)
    try:
        with pytest.raises(JiraTempoError) as exc_info:
            await client._request("GET", "https://jira.test.example/rest/api/2/myself",
                                  client._jira_headers())
    finally:
        await client.aclose()
    assert exc_info.value.status_code == 503
    # No retry attempted — exactly one call.
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_request_5xx_retries_then_succeeds_on_get() -> None:
    """A transient 5xx on idempotent GET retries and recovers.

    Handler returns 503 twice then 200. With http_max_retries=2 the client
    must retry and return the successful body, having made 3 calls total.
    """
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(503, json={"error": "blip"})
        return httpx.Response(200, json={"ok": True})

    client = _client_with_transport(handler, http_max_retries=2)
    try:
        # Patch sleep to keep the test fast — backoff is unit-tested separately.
        import jira_tempo_mcp.client as client_mod

        original_sleep = client_mod.asyncio.sleep
        client_mod.asyncio.sleep = _noop_sleep  # type: ignore[assignment]
        try:
            result = await client._request(
                "GET",
                "https://jira.test.example/rest/api/2/myself",
                client._jira_headers(),
            )
        finally:
            client_mod.asyncio.sleep = original_sleep  # type: ignore[assignment]
    finally:
        await client.aclose()
    assert result == {"ok": True}
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_request_5xx_does_not_retry_on_post() -> None:
    """Non-idempotent methods (POST) must NOT retry on 5xx.

    A 5xx on POST is ambiguous — the server may have committed the write.
    Retrying could create duplicates (e.g. worklogs). Even with
    http_max_retries set, POST must make exactly one call and raise.
    """
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={"error": "service unavailable"})

    client = _client_with_transport(handler, http_max_retries=3)
    try:
        with pytest.raises(JiraTempoError):
            await client._request(
                "POST",
                "https://jira.test.example/rest/tempo-timesheets/4/worklogs",
                client._tempo_headers(),
                json={"some": "body"},
            )
    finally:
        await client.aclose()
    assert calls["n"] == 1, "POST must not be retried on 5xx"


# --- httpx.RequestError (network) surfaces as JiraTempoError ----------------


@pytest.mark.asyncio
async def test_request_network_error_raises() -> None:
    """A network error (httpx.ConnectError) must surface as JiraTempoError.

    With retries disabled (default), the transport raising a RequestError
    must not leak the raw httpx exception — it is wrapped in JiraTempoError.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _client_with_transport(handler, http_max_retries=0)
    try:
        with pytest.raises(JiraTempoError, match="Network error"):
            await client._request(
                "GET",
                "https://jira.test.example/rest/api/2/myself",
                client._jira_headers(),
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_request_network_error_retries_on_get() -> None:
    """A transient network error on idempotent GET retries and recovers.

    Handler raises ConnectError twice then returns 200. With
    http_max_retries=2 the client must retry and succeed (3 calls).
    """
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            raise httpx.ConnectError("transient")
        return httpx.Response(200, json={"ok": True})

    client = _client_with_transport(handler, http_max_retries=2)
    try:
        import jira_tempo_mcp.client as client_mod

        original_sleep = client_mod.asyncio.sleep
        client_mod.asyncio.sleep = _noop_sleep  # type: ignore[assignment]
        try:
            result = await client._request(
                "GET",
                "https://jira.test.example/rest/api/2/myself",
                client._jira_headers(),
            )
        finally:
            client_mod.asyncio.sleep = original_sleep  # type: ignore[assignment]
    finally:
        await client.aclose()
    assert result == {"ok": True}
    assert calls["n"] == 3


# --- .py template code-execution warning -------------------------------------


def test_py_template_warning_logged(tmp_path: Path, caplog: Any) -> None:
    """Loading a .py template under ALLOW_PY=1 must log a code-execution warning.

    The warning is the operator's signal that the .py template runs arbitrary
    code. It must fire on BOTH entry points (discover + REPORT_TEMPLATE_PATH);
    this test covers discover_custom_templates.
    """
    # A minimal but valid .py template exposing a TEMPLATE attribute.
    py_template = tmp_path / "evil.py"
    py_template.write_text(
        "class _T:\n"
        "    name = 'evil'\n"
        "    description = 'test template'\n"
        "    def render(self, worklogs, config, **kwargs):\n"
        "        return 'rendered'\n"
        "TEMPLATE = _T()\n",
        encoding="utf-8",
    )

    config = _make_config(
        report_template_allow_py=True,
        report_template_dir=str(tmp_path),
    )

    from jira_tempo_mcp.templates.loader import discover_custom_templates

    with caplog.at_level(logging.WARNING, logger="jira_tempo_mcp.templates.loader"):
        templates = discover_custom_templates(config)

    # Template loaded.
    assert any(t.name == "evil" for t in templates)
    # The code-execution warning was emitted.
    assert any(
        "executes arbitrary code" in rec.getMessage() or "ensure this file is trusted" in rec.getMessage()
        for rec in caplog.records
    ), "expected code-execution warning for .py template"


# --- helpers -----------------------------------------------------------------


async def _noop_sleep(_seconds: float) -> None:
    """No-op replacement for asyncio.sleep to keep retry tests instant."""
    return None
