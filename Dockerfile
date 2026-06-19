# Multi-stage build for jira-tempo-mcp.
# Secrets are NEVER baked in — pass them at runtime via --env-file or K8s Secret.

# ---------- builder stage ----------
FROM python:3.12-slim AS builder

# Build deps in a clean venv so we can copy only what we need to runtime.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Install build backend first for better layer caching.
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Build a wheel and install it into the venv (no dev deps in runtime image).
RUN pip install --no-cache-dir --upgrade pip build && \
    python -m build --wheel --outdir /dist && \
    pip install --no-cache-dir /dist/jira_tempo_mcp-*.whl

# ---------- runtime stage ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Copy the venv with the installed package from the builder.
COPY --from=builder /opt/venv /opt/venv

# Run as a non-root user. UID 1001 matches the common distroless convention.
RUN useradd --uid 1001 --no-create-home --shell /usr/sbin/nologin appuser
USER 1001

# Healthcheck: verify the package is importable. No network call — the server
# speaks stdio, so there is no HTTP port to probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import jira_tempo_mcp" || exit 1

# Default entrypoint: stdio MCP server. Override args for other subcommands.
ENTRYPOINT ["jira-tempo-mcp"]
CMD ["serve"]