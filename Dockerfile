# ─── uv binary ────────────────────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:latest AS uv

# ─── builder-base: shared deps (migrate · scheduler · recorder) ───────────────
FROM python:3.12-slim AS builder-base
COPY --from=uv /uv /usr/local/bin/uv
ENV VIRTUAL_ENV=/opt/venv PATH="/opt/venv/bin:$PATH"
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN uv venv $VIRTUAL_ENV && uv pip install --no-cache .

# ─── builder-web: base + web framework ────────────────────────────────────────
FROM builder-base AS builder-web
RUN uv pip install --no-cache ".[web]"

# ─── builder-worker: base + network/parsing stack ─────────────────────────────
FROM builder-base AS builder-worker
RUN uv pip install --no-cache ".[worker]"

# ─── runtime-base: migrate · scheduler · recorder ─────────────────────────────
FROM python:3.12-slim AS runtime-base
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=builder-base /opt/venv /opt/venv
WORKDIR /app
COPY alembic.ini .
COPY alembic/ ./alembic/
RUN mkdir -p /var/lib/kiroku/backups
VOLUME ["/var/lib/kiroku/backups"]
ENTRYPOINT ["kiroku"]

# ─── web ──────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS web
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=builder-web /opt/venv /opt/venv
WORKDIR /app
COPY alembic.ini .
COPY alembic/ ./alembic/
EXPOSE 8000
ENTRYPOINT ["kiroku"]
CMD ["serve"]

# ─── worker ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS worker
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates openssh-client \
 && rm -rf /var/lib/apt/lists/*
COPY --from=builder-worker /opt/venv /opt/venv
WORKDIR /app
COPY alembic.ini .
COPY alembic/ ./alembic/
ENTRYPOINT ["kiroku"]
CMD ["worker"]
