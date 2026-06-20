"""Jira + Tempo Timesheets API client.

All HTTP calls go through this module. Tokens are read from Config and never
logged. Errors are redacted before propagation.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import Config

logger = logging.getLogger(__name__)


class JiraTempoError(Exception):
    """Raised on API errors. Message never contains tokens or full URLs with auth."""


class WorkerKeyResolutionError(JiraTempoError):
    """Raised when the Tempo worker key cannot be resolved for the configured user."""


def _redact(url: str) -> str:
    """Strip any credentials from URL for safe logging."""
    if "://" in url and "@" in url.split("://", 1)[1]:
        scheme, rest = url.split("://", 1)
        host = rest.split("@", 1)[1]
        return f"{scheme}://***@{host}"
    return url


class JiraTempoClient:
    """Async HTTP client for Jira REST API and Tempo Timesheets 4 API."""

    def __init__(self, config: Config) -> None:
        self._config = config
        # M1: explicit TLS verification + no redirects (defense-in-depth).
        # follow_redirects=False prevents PAT leakage via redirect to a different host.
        self._client = httpx.AsyncClient(
            timeout=config.http_timeout,
            verify=True,
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> JiraTempoClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    # --- auth headers ---

    def _jira_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._config.jira_pat}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _tempo_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._config.tempo_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # --- low-level request helper ---

    async def _request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        try:
            resp = await self._client.request(
                method, url, headers=headers, json=json, params=params
            )
        except httpx.RequestError as exc:
            raise JiraTempoError(
                f"Network error contacting Jira/Tempo: {exc.__class__.__name__}"
            ) from exc

        if resp.status_code >= 400:
            # m6: truncate to 200 chars to reduce log noise and potential token leakage.
            body = resp.text[:200] if resp.text else ""
            logger.error("API %s %s -> %s: %s", method, _redact(url), resp.status_code, body)
            raise JiraTempoError(f"API error {resp.status_code} from {_redact(url)}: {body}")

        if resp.status_code == 204 or not resp.text:
            return None
        return resp.json()

    # --- Jira issue ---

    async def get_issue(self, issue_key: str) -> dict[str, Any]:
        """Get issue metadata (key, summary, status, project)."""
        url = f"{self._config.jira_api_base}/issue/{issue_key}"
        fields = "summary,status,project,issuetype"
        data = await self._request("GET", url, self._jira_headers(), params={"fields": fields})
        if not isinstance(data, dict):
            raise JiraTempoError(f"Unexpected response for issue {issue_key}")
        return data

    # --- Tempo worklogs ---

    async def search_worklogs(
        self,
        date_from: str,
        date_to: str,
        *,
        worker_keys: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search Tempo worklogs in a date range (ISO dates YYYY-MM-DD).

        Uses POST /worklogs/search (Tempo 4 API). Returns raw worklog objects.
        """
        url = f"{self._config.tempo_api_base}/worklogs/search"
        payload: dict[str, Any] = {"from": date_from, "to": date_to}
        if worker_keys:
            payload["worker"] = worker_keys
        data = await self._request("POST", url, self._tempo_headers(), json=payload)
        if data is None:
            return []
        if isinstance(data, dict) and "results" in data:
            return list(data["results"])
        if isinstance(data, list):
            return data
        raise JiraTempoError("Unexpected worklogs search response shape")

    async def get_worklog(self, worklog_id: str) -> dict[str, Any]:
        """Get a single Tempo worklog by its Tempo internal id."""
        url = f"{self._config.tempo_api_base}/worklogs/{worklog_id}"
        data = await self._request("GET", url, self._tempo_headers())
        if not isinstance(data, dict):
            raise JiraTempoError(f"Unexpected response for worklog {worklog_id}")
        return data

    async def create_worklog(
        self,
        *,
        issue_key: str,
        time_spent_seconds: int,
        date_started: str,  # ISO 8601 with timezone, e.g. 2026-06-19T10:00:00+03:00
        comment: str = "",
        author_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a Tempo worklog.

        issue_key: Jira issue key (e.g. PROJECT-100).
        time_spent_seconds: duration in seconds.
        date_started: ISO 8601 datetime string with timezone offset.
        comment: optional worklog comment.
        author_account_id: Tempo worker key; if None, server uses the token owner.
        """
        url = f"{self._config.tempo_api_base}/worklogs"
        payload: dict[str, Any] = {
            "issueKey": issue_key,
            "timeSpentSeconds": time_spent_seconds,
            "startDate": date_started,
            "comment": comment,
        }
        if author_account_id:
            payload["authorAccountId"] = author_account_id
        data = await self._request("POST", url, self._tempo_headers(), json=payload)
        if not isinstance(data, dict):
            raise JiraTempoError("Unexpected create worklog response")
        return data

    async def delete_worklog(self, worklog_id: str) -> None:
        """Delete a Tempo worklog by id."""
        url = f"{self._config.tempo_api_base}/worklogs/{worklog_id}"
        await self._request("DELETE", url, self._tempo_headers())

    # --- Tempo worker key lookup ---

    async def find_worker_key(self, username: str | None = None) -> str:
        """Find Tempo worker key for a Jira username.

        Tempo 4 API: GET /workers?username=... — returns list of workers.

        Raises WorkerKeyResolutionError if the endpoint is unavailable or the
        worker is not found. This prevents silent empty-result bugs where
        list_worklogs returns [] because the wrong key was used.
        """
        target = username or self._config.jira_user
        url = f"{self._config.tempo_api_base}/workers"
        try:
            data = await self._request(
                "GET", url, self._tempo_headers(), params={"username": target}
            )
        except JiraTempoError as exc:
            raise WorkerKeyResolutionError(
                f"Could not reach Tempo /workers endpoint to resolve worker key "
                f"for {target!r}: {exc}. Set TEMPO_WORKER_KEY env var or check "
                f"Tempo API connectivity."
            ) from exc

        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                key = first.get("key") or first.get("accountId") or first.get("id")
                if key is not None:
                    return str(key)

        raise WorkerKeyResolutionError(
            f"Tempo /workers returned no matching worker for username {target!r}. "
            f"Verify the JIRA_USER is correct or set TEMPO_WORKER_KEY manually."
        )

    # --- favorites (optional convenience) ---

    async def list_favorite_issues(self) -> list[dict[str, Any]]:
        """List favorite issues for the current user via Jira REST API.

        Uses the /user/favourites endpoint for issues. Returns list of
        {key, summary} dicts. May return empty if endpoint is unavailable.
        """
        url = f"{self._config.jira_api_base}/user/favourites"
        try:
            data = await self._request("GET", url, self._jira_headers())
        except JiraTempoError:
            return []
        if not isinstance(data, list):
            return []
        out: list[dict[str, Any]] = []
        for item in data:
            if isinstance(item, dict):
                key = item.get("key")
                fields = item.get("fields", {}) if isinstance(item.get("fields"), dict) else {}
                summary = fields.get("summary", "") if isinstance(fields, dict) else ""
                if key:
                    out.append({"key": key, "summary": summary})
        return out
