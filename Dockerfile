# =============================================================================
# Dryade Core — Production Docker Image
# =============================================================================
# Multi-stage build for minimal image size.
#
# Build:  docker build -t dryade .
# Run:    docker run -p 8080:8080 --env-file .env dryade
#
# Runs as non-root user (dryade) with health check on /api/health.
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder — install Python dependencies
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Install UV package manager for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# System dependencies for building native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy project manifest and install dependencies
COPY dryade-core/pyproject.toml ./dryade-core/pyproject.toml
COPY dryade-core/core/ ./dryade-core/core/

# Create virtual environment and install the package
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install "./dryade-core[knowledge]"

# -----------------------------------------------------------------------------
# Stage 2: Runtime — minimal production image
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Python environment settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Install runtime dependencies (curl, Node.js for MCP servers) and create non-root user
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && adduser --disabled-password --home /app --gecos "" dryade

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy core application source and config
COPY --chown=dryade:dryade dryade-core/core/ ./core/
COPY --chown=dryade:dryade config/ ./config/

# Create data directories
RUN mkdir -p /app/data /app/uploads /app/artifacts && \
    chown -R dryade:dryade /app

# Run as non-root user
USER dryade

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/api/health || exit 1

EXPOSE 8080

# Start the application with uvicorn
CMD ["uvicorn", "core.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
