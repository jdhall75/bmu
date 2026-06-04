# Kiroku

Distributed network device backup and data collection.

## Architecture

Six processes across three Docker images, all driven by the same `kiroku` CLI:

| Process     | Image          | Command            | Role |
|-------------|----------------|--------------------|------|
| `web`       | `web`          | `kiroku serve`     | Litestar + Jinja UI for groups, devices, platforms, jobs, parsers, schedules, runs |
| `scheduler` | `runtime-base` | `kiroku scheduler` | Polls schedules with croniter, single-leader via Postgres advisory lock, enqueues job specs onto a Redis Stream |
| `worker`    | `worker`       | `kiroku worker`    | Consumes the job stream, runs scrapli2 (CLI / NETCONF), publishes results |
| `recorder`  | `runtime-base` | `kiroku recorder`  | Consumes the result stream, commits backups to a git repo, updates run rows |
| `migrate`   | `runtime-base` | `kiroku migrate`   | One-shot Alembic upgrade; runs as an init container before other services start |

Backing services: Postgres (≥14) + Redis (≥7). Backup configs live in a git
repo on a volume mounted into `recorder` (read-write) and `web` (read-only).

## Quick start

```bash
docker compose up --build
# UI at http://localhost:8000
```

## Docker images

The multi-stage `Dockerfile` produces three runtime targets. Each service in
`docker-compose.yml` selects the smallest image that covers its dependencies.

| Target          | System packages          | Python extras         | Used by |
|-----------------|--------------------------|-----------------------|---------|
| `runtime-base`  | git, ca-certificates     | *(base deps only)*    | migrate, scheduler, recorder |
| `web`           | git, ca-certificates     | `.[web]`              | web |
| `worker`        | openssh-client, ca-certs | `.[worker]`           | worker |

Builder stages (`builder-base`, `builder-web`, `builder-worker`) use
[uv](https://github.com/astral-sh/uv) for fast dependency installation and
share a common base layer so incremental rebuilds are cheap.

## Local development

```bash
# Install all extras for local development
uv pip install -e ".[web,worker]"

# Or with pip
pip install -e ".[web,worker]"

# Run the web server against local postgres/redis
KIROKU_DATABASE_URL_SYNC=postgresql+psycopg://bmu:bmu@localhost:5432/bmu \
KIROKU_REDIS_URL=redis://localhost:6379/0 \
kiroku serve
```

## Configuration

All settings are read from environment variables (prefix `KIROKU_`) or a
`.env` file in the working directory. Every variable has a built-in default
so the stack runs out of the box with `docker compose up`.

### Database & Redis

| Variable | Default | Description |
|---|---|---|
| `KIROKU_DATABASE_URL` | `postgresql+psycopg://bmu:bmu@postgres:5432/bmu` | Async SQLAlchemy URL (psycopg3) |
| `KIROKU_DATABASE_URL_SYNC` | `postgresql+psycopg://bmu:bmu@postgres:5432/bmu` | Sync URL used by Alembic migrations |
| `KIROKU_REDIS_URL` | `redis://redis:6379/0` | Redis connection URL |

### Streams

| Variable | Default | Description |
|---|---|---|
| `KIROKU_JOB_STREAM` | `kiroku:jobs` | Redis stream name for job specs |
| `KIROKU_RESULT_STREAM` | `kiroku:results` | Redis stream name for job results |
| `KIROKU_JOB_CONSUMER_GROUP` | `workers` | Redis consumer group for the job stream |
| `KIROKU_RESULT_CONSUMER_GROUP` | `recorders` | Redis consumer group for the result stream |
| `KIROKU_STREAM_MAX_LEN` | `10000` | Hard cap on entries per stream. Applied as `XADD MAXLEN ~` on every write — Redis trims already-consumed entries at natural boundaries. Raise this if large device counts cause batches to be rejected at high-water before workers drain the queue. |
| `KIROKU_STREAM_HIGH_WATER_RATIO` | `0.8` | Fraction of `KIROKU_STREAM_MAX_LEN` at which new batches are refused. When undelivered entries + incoming batch size exceeds `max_len × ratio`, all runs in the batch are immediately marked failed with a clear error visible in the UI. Default `0.8` = refuse at 8 000 undelivered entries (with a 10 000 max). |

### Security

| Variable | Default | Description |
|---|---|---|
| `KIROKU_SECRET_KEY` | *(weak placeholder)* | 32-byte key used to derive the Fernet encryption key for locally-stored credentials. **Must be changed in production.** |

### Storage

| Variable | Default | Description |
|---|---|---|
| `KIROKU_BACKUP_REPO_PATH` | `/var/lib/kiroku/backups` | Absolute path to the on-disk git repo where device configs are stored |

### Scheduler

| Variable | Default | Description |
|---|---|---|
| `KIROKU_SCHEDULER_TICK_SECONDS` | `15` | How often the scheduler wakes to check for due schedules |
| `KIROKU_SCHEDULER_ADVISORY_LOCK_ID` | `1263551311` | Postgres advisory lock ID used for single-leader election |

### Worker

| Variable | Default | Description |
|---|---|---|
| `KIROKU_WORKER_CONCURRENCY` | `8` | Number of concurrent device jobs per worker process |
| `KIROKU_WORKER_CONNECT_TIMEOUT` | `30` | Transport-level socket connect timeout (seconds) |
| `KIROKU_WORKER_COMMAND_TIMEOUT` | `60` | scrapli per-operation timeout in seconds. When exceeded the worker records the failure and moves on without blocking on close. |

### Recorder

| Variable | Default | Description |
|---|---|---|
| `KIROKU_RECORDER_BATCH_TIMEOUT` | `1800` | Seconds after a batch is created before the reaper force-closes it. Set higher than your largest expected batch duration (`devices × command_timeout / concurrency`). |

### Web

| Variable | Default | Description |
|---|---|---|
| `KIROKU_WEB_HOST` | `0.0.0.0` | Bind address for the web server |
| `KIROKU_WEB_PORT` | `8000` | Bind port for the web server |

### Logging

| Variable | Default | Description |
|---|---|---|
| `KIROKU_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `KIROKU_LOG_JSON` | `false` | Emit structured JSON logs instead of human-readable text |

### CVE scanning

| Variable | Default | Description |
|---|---|---|
| `KIROKU_NVD_API_KEY` | *(none)* | NVD API key. Without a key: 1 req/s. With a key: 5 req/s. Obtain at https://nvd.nist.gov/developers/request-an-api-key |

## Platforms

Kiroku uses **scrapli2** for device connectivity. A Platform defines how
scrapli talks to a device: prompt patterns, mode transitions, failure
indicators, and on-open / on-close instructions. Platform definitions are YAML
files passed to scrapli's `Cli(definition_file_or_name=…)`.

Built-in platforms (bundled with scrapli2):

- `cisco_iosxe`, `cisco_iosxr`, `cisco_nxos`, `cisco_asa`
- `arista_eos`
- `juniper_junos`

For any other vendor (Nokia SR Linux, Mikrotik, Adtran, Calix, etc.) create a
**Custom Platform** at `/platforms/new`. The form includes an annotated YAML
example and a full field reference.

## Jobs

A Job defines *what* to do and *which devices* to target:

| Kind       | Purpose |
|------------|---------|
| `backup`   | Capture the running config and store it in Git |
| `collect`  | Run one or more commands and optionally parse the output with a Parser template |
| `cve_scan` | Detect the OS version and cross-reference it with NVD |

Jobs can be triggered immediately from the job list or run on a recurring basis
via a Schedule. The ▶ button on the job list fires a one-off run without needing
a schedule.

## Parser templates

A Parser template normalizes unstructured command output into structured rows.
Supported engines: **TextFSM**, **TTP**, **XSLT** (for NETCONF XML).

Use the **Test bed** (`/parsers/test`) to iterate quickly — paste real device
output in the left pane, write the template on the right, and hit Run to see
parsed output immediately.

## Credentials

Credentials are referenced by name; the actual secret is fetched at job
execution time from a configurable provider:

| Provider    | Status    | Notes |
|-------------|-----------|-------|
| `local`     | Available | Fernet-encrypted blob in Postgres; key derived from `KIROKU_SECRET_KEY` |
| `vault`     | Planned   | HashiCorp Vault KV v2; ABC in place |
| `bitwarden` | Planned   | Bitwarden Secrets Manager; ABC in place |

One credential can be marked as the **default fallback**, used automatically
for any device or group that has no credential explicitly assigned.

The job spec published to the Redis stream carries only `(provider, credential_id, ref)` — never the secret material itself.

## Config search

Every successful backup is indexed in Postgres (`device_configs` table) with:

- A `tsvector` GIN index for full-text keyword search (`websearch_to_tsquery`)
- A `pg_trgm` GIN index for exact-substring search (IP addresses, interface names, ACL names)

Search is available at `/search` with configurable result context lines.
