# Getting Started — Kiroku Workflow

Kiroku is a network device configuration management system. It connects to routers and switches via SSH/Telnet or NETCONF, backs up their running configurations to a Git repository, collects structured operational data, and scans for known software vulnerabilities.

## How the pieces fit together

```
Credentials  ──►  Groups  ──►  Jobs  ──►  Schedules
                     │           │
Platforms ───►  Devices ◄──  Parsers
                                 │
                              Runs ──► Config history / Search / CVE
```

Each arrow represents a dependency. Before you can create something, the things it points to must already exist.

## Setup order

Follow this sequence when setting up Kiroku for the first time.

### 1. Credentials

Go to **Credentials → New credential** and create at least one set of login details.

- For lab environments, mark one credential as **Default fallback** — it will be used automatically for any device or group that has no credential assigned.
- For production, assign credentials explicitly to groups or individual devices.

### 2. Platforms (optional)

Skip this step if your devices are covered by scrapli's built-in platforms: `cisco_iosxe`, `cisco_iosxr`, `cisco_nxos`, `arista_eos`, `juniper_junos`, and others.

Go to **Platforms → New platform** only if you have a vendor not in that list. You write a YAML definition that teaches scrapli what the prompt looks like and how to navigate between modes.

### 3. Groups

Go to **Groups → New group** and create a logical grouping for your devices (e.g. by site, vendor, or function).

- Assign a **Default credential** — every device in the group inherits it.
- **Max parallel** controls how many devices are worked simultaneously during a job run. Start conservatively (4–8) and raise it once you know your network handles the load.

### 4. Devices

Go to **Devices → New device** (or use **Bulk import** to paste a CSV).

- Assign each device to one or more groups.
- Select a **Platform** — either a built-in scrapli platform name or a custom platform you defined in step 2.
- Leave **Credential override** as *(use group default)* unless this device needs its own login.
- Set **Driver kind** to `netconf` only for NETCONF-capable devices; leave it as `cli` for everything else.

### 5. Parser templates (optional, for collect jobs)

Skip if you only need config backups.

Go to **Parsers → New parser template** and write a TextFSM, TTP, or XSLT template that extracts structured data from command output (e.g. `show version`, `show interfaces`).

Use the **Test bed** (`/parsers/test`) to iterate quickly — paste real device output in the left pane, write the template in the right pane, and hit **Run** (or Ctrl+Enter) to see the parsed result before saving.

### 6. Jobs

Go to **Jobs → New job** and define what to do.

| Kind | Purpose |
|------|---------|
| `backup` | Capture the running config and store it in Git |
| `collect` | Run commands and optionally parse the output with a template |
| `cve_scan` | Detect the OS version and cross-reference it with NVD |

- Add the **Device groups** or individual **Devices** this job should target.
- For `collect` jobs, select a **Parser template** if you want structured output.
- For `cve_scan` jobs, fill in the **CVE vendor** and **CVE product** fields (e.g. `cisco` / `ios_xe`).

A job can be run immediately with the **Run now** button on the job list, without needing a schedule.

### 7. Schedules

Go to **Schedules → New schedule** to automate a job on a recurring basis.

- Pick the **Job** to run.
- Enter a **cron expression** (e.g. `0 2 * * *` = every night at 2 AM).
- Set the **Timezone** using an IANA name like `America/Chicago` or `Europe/London`.

## Common workflows

### Back up device configurations nightly

1. Create credentials → group → devices
2. Create a `backup` job targeting the group
3. Create a schedule: `0 3 * * *`
4. After the first run, browse config history at **Devices → [device] → Git History**

### Collect and parse operational data

1. Create a `collect` job with the commands you want to run
2. Create a parser template that matches the output format
3. Attach the parser template to the job
4. Run the job — navigate to the batch, click the ✓ in the Parsed column to see structured rows

### Scan for CVEs

1. Create a `cve_scan` job with a command that shows the OS version (e.g. `show version`)
2. Create a TextFSM or TTP parser that extracts a `version` field
3. Set the **CVE vendor** and **CVE product** on the job
4. Run the job — results appear in **CVE Scans**

### Search stored configurations

Use **Search** to find any text across all backed-up device configs. Use **Exact** mode for IP addresses and interface names; use **Full-text** for keywords that may appear in inflected forms.

## Tuning for large device inventories

### Stream capacity

Jobs are queued through a Redis Stream before workers pick them up. Two settings control how large that queue can grow:

| Variable | Default | When to change |
|---|---|---|
| `KIROKU_STREAM_MAX_LEN` | `10000` | Increase if you have a very large device inventory and batches are being rejected (see below). Decrease to reduce Redis memory usage on small deployments. |
| `KIROKU_STREAM_HIGH_WATER_RATIO` | `0.8` | Fraction of max length at which new batches are refused. Lower this to leave more headroom; raise it if you want to allow the queue to fill closer to the hard cap before blocking. |

**What happens when the queue is full:** if the number of undelivered jobs in the stream plus the incoming batch size would exceed `KIROKU_STREAM_MAX_LEN × KIROKU_STREAM_HIGH_WATER_RATIO`, the entire batch is rejected before any jobs are published. All runs in the batch are immediately marked **Failed** with a message explaining the rejection and telling you to retry when workers catch up. The batch is visible in the run history so you can see exactly when and why it was refused.

**Sizing guidance:** the default 10 000-entry cap with the 128 MB Redis memory limit (set in `docker-compose.yml`) comfortably handles inventories of several thousand devices. If a single scheduled batch exceeds `max_len × high_water_ratio` devices, either raise `KIROKU_STREAM_MAX_LEN` or split the job into smaller device groups.
