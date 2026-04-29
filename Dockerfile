FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git ca-certificates curl openssh-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src

RUN pip install --upgrade pip && pip install -e .

RUN mkdir -p /var/lib/bmu/backups
VOLUME ["/var/lib/bmu/backups"]

EXPOSE 8000

ENTRYPOINT ["bmu"]
CMD ["serve"]
