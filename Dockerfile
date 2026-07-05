# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.13-slim-bookworm AS runtime

# Toolchain the agent's sandboxed shell needs: git for version control,
# curl/ca-certificates for fetching, tree for directory listings (it's on
# the read-only allowlist in app/services/action_parser.py).
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash \
        git \
        curl \
        ca-certificates \
        tree \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

RUN groupadd --gid 1000 sage \
    && useradd --uid 1000 --gid sage --create-home --shell /bin/bash sage

WORKDIR /app
COPY --from=builder --chown=sage:sage /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WORKSPACE=/workspace \
    DB_PATH=/data/agent.db

RUN mkdir -p /workspace /data && chown -R sage:sage /workspace /data

USER sage

CMD ["sage"]
