# Deployment

Docker build, CI/CD pipelines, and the release workflow.

## Docker

### Build the image locally

```bash
docker build -t jira-tempo-mcp .
```

The `Dockerfile` is a **multi-stage build**:

| Stage | Base | What happens |
| --- | --- | --- |
| `builder` | `python:3.12-slim` | Build a wheel, install it into a clean venv (no dev deps) |
| `runtime` | `python:3.12-slim` | Copy only the venv, run as non-root `appuser` (UID 1001) |

Runtime env: `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`.

A `HEALTHCHECK` verifies the package is importable
(`python -c "import jira_tempo_mcp"`). There is no HTTP port to probe — the
server speaks stdio.

### Run the container

```bash
# stdio mode — pipe JSON-RPC in/out
docker run -i --rm \
  --env-file .env \
  jira-tempo-mcp

# or use the published image
docker run -i --rm \
  --env-file .env \
  ghcr.io/korrnals/jira-tempo-mcp:latest
```

### Required environment variables

Pass them via `--env-file` (a gitignored `.env`) or a Kubernetes Secret:

| Variable | Required | Description |
| --- | --- | --- |
| `JIRA_BASE_URL` | yes | Jira base URL (no trailing slash) |
| `JIRA_USER` | yes | Jira username |
| `JIRA_PAT` | yes | Personal Access Token |
| `JIRA_TIMEZONE` | no | IANA timezone (default `Europe/Moscow`) |
| `TEMPO_API_TOKEN` | no | Separate Tempo token (falls back to `JIRA_PAT`) |
| `LOG_LEVEL` | no | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `JIRA_HTTP_TIMEOUT` | no | HTTP timeout in seconds (default `30.0`) |
| `REPORT_OUTPUT_DIR` | no | Base directory for reports (default `./reports`) |
| `REPORT_AUTHOR_NAME` | no | Author name in report header (default `JIRA_USER`) |
| `REPORT_SECTION_MAP` | no | JSON dict: issue key → section title |
| `REPORT_SECTION_MAP_FILE` | no | Path to a JSON file with the section mapping |
| `REPORT_FILENAME_PREFIX` | no | Prefix for report filenames (default `JIRA_USER`) |
| `REPORT_STABLE_ORDER` | no | JSON list: issue keys in stable order |
| `REPORT_NON_ISSUE_SECTIONS` | no | JSON list: non-issue section titles |

> **Never** bake `JIRA_PAT` into the image. The `.dockerignore` excludes
> `.env`, `.venv/`, `.history/`, and build artifacts from the build context.

See [configuration.md](configuration.md) for the full variable reference.

## CI/CD

The repo has two GitHub Actions workflows:

| Workflow | Trigger | What it does |
| --- | --- | --- |
| [`ci.yml`](../.github/workflows/ci.yml) | push / PR to `main` | `ruff check` + `ruff format --check` + `mypy src/` + `pytest tests/ -v` on Python 3.12 |
| [`release.yml`](../.github/workflows/release.yml) | git tag `v*` | Build wheel, build & push Docker image to `ghcr.io/korrnals/jira-tempo-mcp:<tag>`, create GitHub Release |

CI uses the ruff / mypy / pytest configuration from `pyproject.toml` — no
duplicated config. Pip dependencies are cached via `actions/setup-python`
keyed on `pyproject.toml`.

### CI pipeline detail

```mermaid
flowchart LR
    A[push / PR to main] --> B[checkout]
    B --> C[setup-python 3.12<br/>cache: pip]
    C --> D[pip install -e .[dev]]
    D --> E[ruff check]
    D --> F[ruff format --check]
    D --> G[mypy src/]
    D --> H[pytest tests/ -v]
```

Concurrency: `ci-${{ github.ref }}` with `cancel-in-progress: true` — a new
push cancels the previous run on the same branch.

## Release process

```bash
# 1. Bump version in pyproject.toml
# 2. Commit + push to main (CI must be green)
# 3. Tag and push
git tag v0.2.0
git push origin v0.2.0
```

The release workflow then:

1. Builds the wheel and sdist (`python -m build`).
2. Builds the Docker image and pushes it to
   `ghcr.io/korrnals/jira-tempo-mcp:v0.2.0` (and `:latest` for non-pre-release
   tags).
3. Creates a GitHub Release with auto-generated release notes and the wheel
   attached as a download asset.

### Release pipeline detail

```mermaid
flowchart LR
    A[tag v* pushed] --> B[build-wheel job]
    A --> C[docker job]
    B --> D[python -m build]
    D --> E[upload artifact]
    C --> F[docker/buildx-action]
    F --> G[login to ghcr.io]
    G --> H[build + push image]
    E --> I[create GitHub Release]
    H --> I
```

Permissions required by `release.yml`:

| Permission | Why |
| --- | --- |
| `contents: write` | create GitHub Release + upload wheel asset |
| `packages: write` | push image to ghcr.io |

## Pre-commit hooks

The project ships a `.pre-commit-config.yaml` that runs lint and type
checks before every commit:

```bash
pip install -e ".[dev]"
pre-commit install
```

| Hook | What it does |
| --- | --- |
| `ruff check --fix` | Lint + autofix |
| `ruff format --check` | Verify formatting |
| `mypy src/` | Strict type check on `src/` |
| `trailing-whitespace` / `end-of-file-fixer` / `check-yaml` / `check-added-large-files` | Standard hygiene |

Bypass in an emergency: `git commit --no-verify` (use sparingly).

## Next steps

- [installation.md](installation.md) — local install paths
- [architecture.md](architecture.md#docker-build-safety) — Docker security model
- [configuration.md](configuration.md) — env vars for the container
