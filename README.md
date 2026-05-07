# Kiroku

Distributed network device backup and data collection.

## Architecture

Five processes, all packaged in one image (`kiroku` CLI):

| Process     | Command            | Role                                                                          |
|-------------|--------------------|-------------------------------------------------------------------------------|
| `web`       | `kiroku serve`     | Litestar + Jinja UI for groups, devices, platforms, profiles, schedules, runs |
| `scheduler` | `kiroku scheduler` | Polls schedules with `croniter`, single-leader via Postgres advisory lock, enqueues job specs onto a Redis Stream |
| `worker`    | `kiroku worker`    | Consumes the job stream, runs scrapli2 (CLI / NETCONF), publishes results     |
| `recorder`  | `kiroku recorder`  | Consumes the result stream, commits backups to a git repo, updates run rows   |
| `migrate`   | `kiroku migrate`   | One-shot Alembic upgrade (run by the `web` container's entrypoint)            |

Backing services: Postgres (≥14) + Redis (≥7). Backup configs live in a git
repo on a volume mounted into the `recorder` (and `web`, read-only) containers.

## Quick start

```bash
docker compose up --build
# UI at http://localhost:8000
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
| `KIROKU_WORKER_CONNECT_TIMEOUT` | `30` | Reserved for transport-level socket connect timeout (seconds) |
| `KIROKU_WORKER_COMMAND_TIMEOUT` | `60` | scrapli per-operation timeout in seconds (covers auth + each command). When exceeded, scrapli raises `OperationException: TimeoutExceeded`; the worker records the failure and returns immediately without blocking on close. |

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

## Platforms and Profiles

### Platforms

Kiroku uses **scrapli2** for device connectivity. A Platform defines how
scrapli talks to a device: prompt patterns, mode transitions (exec →
configuration → etc.), failure indicators, and on-open / on-close
instructions. Platform definitions are YAML files passed to scrapli's
`Cli(definition_file_or_name=…)`.

Built-in platforms (bundled in scrapli2):

- `cisco_iosxe`, `cisco_iosxr`, `cisco_nxos`, `cisco_asa`
- `arista_eos`
- `juniper_junos`

For any other vendor (Nokia SR Linux, Mikrotik, Adtran, Calix, etc.) create
a **Custom Platform** at `/platforms/new`. The form includes an annotated
YAML example and a full field reference.

### Profiles

A Profile maps a platform to a set of commands:

- **CLI profiles** — reference a built-in or custom platform, a transport
  (`ssh` / `telnet`), and the commands to run (e.g. `show running-config`).
- **NETCONF profiles** — carry a raw RPC XML payload and an optional XSLT
  transform.

Both kinds may attach a **parser template** (TextFSM or TTP) to normalize
unstructured output into structured rows, and CVE vendor/product hints for
automated vulnerability scanning.

## Credentials

Credentials are referenced by name; the actual secret is fetched at job
execution time from a configurable provider:

| Provider | Status | Notes |
|---|---|---|
| `local` | Available | Fernet-encrypted blob in Postgres; key derived from `KIROKU_SECRET_KEY` |
| `vault` | Planned | HashiCorp Vault KV v2; ABC in place |
| `bitwarden` | Planned | Bitwarden Secrets Manager; ABC in place |

The job spec published to the Redis stream carries only `(provider, credential_id, ref)` — never the secret material itself.

## Config search

Every successful backup is indexed in Postgres (`device_configs` table) with:

- A `tsvector` GIN index for full-text keyword search (`websearch_to_tsquery`)
- A `pg_trgm` GIN index for exact-substring search (IP addresses, interface names, ACL names)

Search is available at `/search` with configurable result context lines.
