"""Allow running as `python -m jira_tempo_mcp [serve|install]`."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
