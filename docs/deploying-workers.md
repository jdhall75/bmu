# Deploying Remote Workers

Kiroku workers are **database-free**. They only need:

1. Outbound TCP to the central Redis instance (job/result streams)
2. Outbound SSH or NETCONF to the managed devices in their local segment

This makes it straightforward to place workers inside firewalled network
segments, DMZs, or remote sites without exposing the PostgreSQL database.

---

## Architecture

```
                    ┌─────────────────────────────────┐
                    │  Central site                   │
                    │                                 │
  Browser ──HTTPS──▶│  web          PostgreSQL        │
                    │  scheduler ──▶ (DB only here)   │
                    │  recorder  ──▶                  │
                    │                                 │
                    │  Redis (TLS + AUTH)  ◀──────────┼──── remote workers
                    └─────────────────────────────────┘
                                                          │
                    ┌─────────────────────────┐          │
                    │  Remote site            │          │
                    │                         │          │
                    │  worker ───────────────────────────┘
                    │     │ SSH/NETCONF                 
                    │     ▼                             
                    │  network devices                  
                    └─────────────────────────┘
```

**Data flow:**

1. `scheduler` reads the schedule from PostgreSQL, calls `dispatcher`.
2. `dispatcher` (inside `web` or `scheduler`) resolves credentials from the
   database and embeds them in the `JobSpec`.
3. `JobSpec` is written to the Redis `kiroku:jobs` stream.
4. A worker anywhere on the network reads the spec from Redis, SSHes to the
   device, and writes a `JobResult` back to `kiroku:results`.
5. `recorder` (central) reads results, writes run rows to PostgreSQL, and
   commits config snapshots to the git repo.

Credentials travel inside the Redis stream as JSON.  **Securing Redis with
TLS and AUTH is mandatory for any deployment where workers are not on the
same trusted host as the server.**

---

## Requirements

### Central site

| Component | Requirement |
|-----------|-------------|
| PostgreSQL 14+ | Unchanged from a single-site deployment |
| Redis 7+ | Must be configured with TLS and AUTH (see below) |
| `web` / `scheduler` / `recorder` | Unchanged — keep `KIROKU_DATABASE_URL_SYNC` set |

### Remote worker host

| Requirement | Notes |
|-------------|-------|
| Docker (or `uv`/pip with Python 3.12) | To run the worker container |
| Outbound TCP to Redis port | Default 6380 for TLS |
| Outbound TCP 22 (SSH) or 830 (NETCONF) | To the managed devices in scope |
| **No** inbound ports required | Workers are outbound-only |
| **No** database access | Never needed |
| **No** shared filesystem | Configs are shipped back through Redis |

---

## Securing Redis with TLS and AUTH

### 1. Generate a CA and server certificate

Run this on the central site (or a dedicated PKI host):

```bash
# Create a local CA
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 \
  -subj "/CN=Kiroku Redis CA" -out ca.crt

# Create a server key and CSR
openssl genrsa -out redis-server.key 4096
openssl req -new -key redis-server.key \
  -subj "/CN=redis.central.example.com" \
  -out redis-server.csr

# Sign the server certificate
openssl x509 -req -in redis-server.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out redis-server.crt -days 825 -sha256
```

For the SAN (Subject Alternative Name) — required by modern TLS clients —
add a `-extfile` with `subjectAltName = DNS:redis.central.example.com,IP:10.0.1.5`.

```bash
cat > san.ext <<EOF
subjectAltName = DNS:redis.central.example.com,IP:10.0.1.5
EOF

openssl x509 -req -in redis-server.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out redis-server.crt -days 825 -sha256 \
  -extfile san.ext
```

### 2. Configure Redis for TLS + AUTH

Add to `redis.conf`:

```
# TLS port (disable plaintext port for production)
port 0
tls-port 6380

tls-cert-file /etc/redis/tls/redis-server.crt
tls-key-file  /etc/redis/tls/redis-server.key
tls-ca-cert-file /etc/redis/tls/ca.crt

# Require clients to present a valid certificate
tls-auth-clients yes

# Require password authentication in addition to TLS
requirepass your-strong-redis-password-here

# Optional: restrict to TLS 1.2+
tls-protocols "TLSv1.2 TLSv1.3"
```

For Docker, mount the certificates into the Redis container and pass the
config file:

```yaml
# In docker-compose.yml (central site)
redis:
  image: redis:7-alpine
  command: redis-server /etc/redis/redis.conf
  volumes:
    - ./certs/redis-server.crt:/etc/redis/tls/redis-server.crt:ro
    - ./certs/redis-server.key:/etc/redis/tls/redis-server.key:ro
    - ./certs/ca.crt:/etc/redis/tls/ca.crt:ro
    - ./redis.conf:/etc/redis/redis.conf:ro
  ports:
    - "6380:6380"
```

Update `KIROKU_REDIS_URL` for all central services:

```
KIROKU_REDIS_URL=rediss://:your-strong-redis-password-here@redis:6380/0
```

The `rediss://` scheme (double-s) enables TLS.

### 3. Client certificate for workers (optional but recommended)

If you set `tls-auth-clients yes` in Redis, each client must present a
certificate signed by your CA.

```bash
# Generate a worker client certificate
openssl genrsa -out worker-client.key 4096
openssl req -new -key worker-client.key \
  -subj "/CN=kiroku-worker" -out worker-client.csr
openssl x509 -req -in worker-client.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out worker-client.crt -days 825 -sha256
```

The Python `redis` library reads TLS client certs through the `ssl_certfile`
and `ssl_keyfile` parameters.  Pass them via the Redis URL:

```
rediss://:password@redis.central.example.com:6380/0?ssl_certfile=/certs/worker-client.crt&ssl_keyfile=/certs/worker-client.key&ssl_ca_certs=/certs/ca.crt
```

Or set `KIROKU_REDIS_SSL_CERTFILE`, `KIROKU_REDIS_SSL_KEYFILE`, and
`KIROKU_REDIS_SSL_CA_CERTS` environment variables if you extend `Settings`
to pass them through.

If you prefer simpler AUTH-only (password, no mutual TLS), set
`tls-auth-clients no` in `redis.conf` and drop the client cert.

---

## Deploying a Remote Worker

### Option A — Docker Compose (recommended)

Copy `docker-compose.worker.yml` and the `ca.crt` to the remote host.

```bash
# On the remote worker host
mkdir -p /opt/kiroku-worker/certs
scp ca.crt remote-host:/opt/kiroku-worker/certs/
scp docker-compose.worker.yml remote-host:/opt/kiroku-worker/

# On the remote host
cd /opt/kiroku-worker
cat > .env <<EOF
KIROKU_IMAGE=your-registry/kiroku-worker:latest
KIROKU_REDIS_URL=rediss://:your-strong-redis-password-here@redis.central.example.com:6380/0
KIROKU_WORKER_CONCURRENCY=8
KIROKU_CERT_DIR=/opt/kiroku-worker/certs
EOF

docker compose -f docker-compose.worker.yml up -d
```

### Option B — Direct Python (no Docker)

On the remote host (Python 3.12+ required):

```bash
pip install "kiroku[worker]"

export KIROKU_REDIS_URL="rediss://:password@redis.central.example.com:6380/0"
export KIROKU_WORKER_CONCURRENCY=8
export SSL_CERT_FILE=/path/to/ca.crt

kiroku worker
```

### Option C — systemd service

```ini
# /etc/systemd/system/kiroku-worker.service
[Unit]
Description=Kiroku remote worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=kiroku
Environment=KIROKU_REDIS_URL=rediss://:password@redis.central.example.com:6380/0
Environment=KIROKU_WORKER_CONCURRENCY=8
Environment=SSL_CERT_FILE=/etc/kiroku/certs/ca.crt
ExecStart=/opt/kiroku-venv/bin/kiroku worker
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable --now kiroku-worker
```

---

## Firewall Rules

### Central site — Redis host

| Direction | Protocol | Port | Source |
|-----------|----------|------|--------|
| Inbound | TCP | 6380 | Worker host IPs only |

### Remote worker host

| Direction | Protocol | Port | Destination |
|-----------|----------|------|-------------|
| Outbound | TCP | 6380 | Central Redis |
| Outbound | TCP | 22 | Managed devices (SSH) |
| Outbound | TCP | 830 | Managed devices (NETCONF) |
| Outbound | TCP | 23 | Managed devices (Telnet — avoid) |

Workers require **no inbound ports**.

---

## Scaling Workers

Multiple workers can consume from the same Redis stream simultaneously.
Redis Streams consumer groups distribute jobs across all active consumers —
add workers freely without coordination.

```
Site A:   2 workers  ─┐
Site B:   4 workers  ──┤──▶  Redis streams  ──▶  recorder
Site C:   1 worker   ─┘
```

Each worker identifies itself with a unique consumer name (`worker-<PID>`).
If a worker crashes mid-job, the recorder's stale-batch reaper (runs every
60 seconds) will mark the run as failed after `KIROKU_RECORDER_BATCH_TIMEOUT`
seconds (default 1800).

To run multiple workers per host, use `KIROKU_WORKER_CONCURRENCY` rather than
multiple containers — the worker already fans out jobs to a `ProcessPoolExecutor`.

---

## Worker Pools — Pinning Devices to Specific Workers

By default all workers share a single job stream (`kiroku:jobs`) and any
worker can execute any job. **Worker pools** let you pin specific devices or
groups to workers at a particular network location.

### How it works

Each job carries a `worker_pool` label derived at dispatch time:

```
device.worker_pool  →  group.worker_pool  →  None (default pool)
```

The dispatcher publishes to `kiroku:jobs:<pool>` instead of `kiroku:jobs`.
Workers set `KIROKU_WORKER_POOL=<pool>` to subscribe to only that stream.
A worker with no pool set reads from `kiroku:jobs` (the default stream).

### Configuring pools

In the UI:
- **Devices → Edit device** — set *Worker pool* on the device to override its group.
- **Groups → Edit group** — set *Worker pool* on the group; all member devices
  inherit it unless they have their own override.

In CSV import — add a `worker_pool` column:
```csv
name,hostname,...,worker_pool
edge-rtr-01,10.0.0.1,...,site-a
dmz-fw-01,192.168.1.1,...,dmz
core-sw-01,10.10.0.1,...,
```
A blank cell leaves an existing device's pool unchanged (new devices get no pool = default).

### Example — three-site deployment

```
Central:  KIROKU_WORKER_POOL unset   → reads kiroku:jobs        (HQ devices)
Site A:   KIROKU_WORKER_POOL=site-a  → reads kiroku:jobs:site-a
DMZ:      KIROKU_WORKER_POOL=dmz     → reads kiroku:jobs:dmz
```

Redis streams for each pool are created automatically on first use
(`XGROUP CREATE ... MKSTREAM`). You can add a pool at any time — just start
a worker with the new pool name and assign devices to it in the UI.

---

## Environment Variable Reference (worker only)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `KIROKU_REDIS_URL` | Yes | — | Redis connection URL (`rediss://` for TLS) |
| `KIROKU_WORKER_POOL` | No | — | Pool name this worker handles (e.g. `site-a`). Unset = default pool |
| `KIROKU_WORKER_CONCURRENCY` | No | `8` | Max concurrent device jobs |
| `KIROKU_WORKER_CONNECT_TIMEOUT` | No | `30` | SSH/NETCONF connect timeout (seconds) |
| `KIROKU_WORKER_COMMAND_TIMEOUT` | No | `60` | Per-command timeout (seconds) |
| `SSL_CERT_FILE` | If TLS | — | Path to CA bundle for Redis TLS verification |
| `KIROKU_LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `KIROKU_LOG_JSON` | No | `false` | Emit structured JSON logs |

Variables the worker does **not** need (and should not be given):

- `KIROKU_DATABASE_URL_SYNC` — no database connection
- `KIROKU_DATABASE_URL` — no database connection
- `KIROKU_SECRET_KEY` — credentials are resolved centrally before dispatch
- `KIROKU_BACKUP_REPO_PATH` — config capture happens in the recorder

---

## Security Notes

- **Credentials travel inside the Redis stream.** The dispatcher resolves
  credentials (including Vault/Bitwarden lookups) before publishing the job,
  and the resolved username/password/key is embedded in the stream message.
  TLS on Redis is not optional for any multi-site deployment.

- **Workers do not know the `KIROKU_SECRET_KEY`.** Fernet decryption of
  locally-stored credentials happens in the dispatcher (central). A
  compromised remote worker cannot decrypt the credential store.

- **Redis AUTH controls who can submit and read jobs.** A worker that can
  authenticate to Redis can both read jobs (execute SSH sessions) and write
  results (falsify run outcomes). Treat the Redis password with the same care
  as a database password.

- **SSH strict host-key checking is disabled** in the scrapli driver
  (`enable_strict_key=False`). This is the standard for network automation
  at scale. If your security policy requires it, enable it in a custom
  platform definition and maintain a `known_hosts` file on the worker host.
