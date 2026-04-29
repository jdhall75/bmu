# BackMeUp (BMU)

Distributed network device backup and data collection.

## Architecture

Five processes, all packaged in one image (`bmu` CLI):

| Process     | Command           | Role                                                                             |
|-------------|-------------------|----------------------------------------------------------------------------------|
| `web`       | `bmu serve`       | Litestar + Jinja UI for managing groups, devices, profiles, schedules, runs.     |
| `scheduler` | `bmu scheduler`   | Polls schedules with `croniter`, single-leader via Postgres advisory lock,       |
|             |                   | enqueues job specs onto a Redis Stream.                                          |
| `worker`    | `bmu worker`      | Consumes the job stream, runs scrapli (CLI / NETCONF), publishes results.        |
| `recorder`  | `bmu recorder`    | Consumes the result stream, commits backups to a git repo, updates run rows.    |
| `migrate`   | `bmu migrate`     | One-shot Alembic upgrade (run by the `web` container's entrypoint).              |

Backing services: Postgres + Redis. Backup configs live in a git repo on a
volume mounted into the `recorder` (and `web`, read-only) containers.

## Quick start

```bash
docker compose up --build
# UI on http://localhost:8000
```

## Profiles

Each device references a **Profile** describing how to talk to it.

- **CLI profiles** point at a `scrapli` platform (e.g. `cisco_iosxe`,
  `arista_eos`, `juniper_junos`). For unknown gear, set `platform = "generic"`
  and supply prompt pattern / pre-commands / paging-disable.
- **NETCONF profiles** describe the RPC to send and an optional XSLT to
  transform the result before storage.

Both kinds may attach a parser template (TextFSM or TTP) so unstructured
output is normalized to a row set.

## Credentials

Credentials are referenced by name; the actual secret is fetched at job
execution time from a configurable provider:

- `local`   - encrypted blob in Postgres (Fernet, key from `BMU_SECRET_KEY`)
- `vault`   - HashiCorp Vault KV v2 (planned, ABC in place)
- `bitwarden` - Bitwarden Secrets Manager (planned, ABC in place)

The job spec on the Redis stream carries only `(provider, ref)`, never the
secret material.
