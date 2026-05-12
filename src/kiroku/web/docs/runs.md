# Runs

A **run** is one execution of a job against one device. Runs are grouped into **batches** — one batch per job firing (whether scheduled or manual).

## Batch list (`/runs`)

Shows all batches, newest first. Each row represents one job firing:

| Column | Notes |
|--------|-------|
| **Schedule** | The schedule name (or job name for ad-hoc runs). Links to the batch detail. |
| **Kind** | `backup`, `collect`, or `cve_scan`. |
| **Started / Finished** | Wall-clock times for the batch. A batch starts when the first run is dispatched and finishes when the last result is recorded. |
| **Total / OK / Failed** | Device counts. A batch is considered partially failed if any device fails. |
| **Status** | Live badge showing the batch state. Updates automatically while the batch is running (HTMx polling). |
| **Commit** | For `backup` batches, the first 8 characters of the Git commit created when any config changed. |

## Batch detail

Click a batch to see per-device results. While the batch is running, the page polls the server every 2 seconds and updates the table automatically — you do not need to refresh.

Per-device columns:

| Column | Notes |
|--------|-------|
| **Device** | Links to the device detail page. |
| **Status** | `pending` → `running` → `success` or `failed`. |
| **Started / Finished** | Times for this specific device's run. |
| **Bytes** | Bytes of config captured (backup) or command output received (collect). |
| **Parsed** | A ✓ link if parsed data is available. Click to view the structured rows. |
| **Error** | Truncated error message if the run failed. Click to see the full error on the run detail page. |

## Run detail

The individual run page shows:

- **Status, Kind, Started, Finished** — basic metadata.
- **Captured** — bytes received from the device.
- **Git commit** — for backup runs, the sha of the commit that recorded this config (if the config changed).
- **Payload SHA256** — hash of the captured content, useful for detecting duplicates.
- **Error** — full error message and traceback for failed runs.
- **Parsed output** — for collect/cve_scan runs with a parser template, the structured rows rendered as a table. Raw JSON is shown if the output is not a list of dicts.

## Run status values

| Status | Meaning |
|--------|---------|
| `pending` | Queued, not yet picked up by a worker |
| `running` | Worker has connected and is executing commands |
| `success` | All commands completed without error |
| `failed` | Connection failed, a command returned an error, or the parser raised an exception |
| `timeout` | Reserved for future use |
| `cancelled` | Reserved for future use |

## Backup runs and Git

For `backup` jobs, Kiroku writes the captured config to a file in a local Git repository (path configured by `KIROKU_GIT_REPO`). The file structure is:

```
<group-name>/<device-name>.txt
```

Individual (non-batch) backup runs commit immediately. Batch backup runs stage all changed files and commit them together when the last device finishes, creating one Git commit for the whole batch. This keeps the history clean.

If no device config changed since the last run, no commit is created (the Git working tree is clean after staging).

## Stale batch handling

If a worker process is killed mid-job, one or more runs may never publish a result. The recorder runs a background reaper that checks every 60 seconds for batches that have been open longer than the configured timeout (default: 30 minutes). When it finds one:

1. Any staged files are committed (partial backup).
2. The batch is marked finished.
3. Any still-pending or still-running device runs are marked `failed` with the error "batch timed out: result never received from worker".

This prevents the batch detail page from showing "running" forever.

## Tips

- Click the **✓** in the Parsed column only appears if a parser template was attached to the job *and* the run succeeded. A successful collect run without a parser shows no ✓ but is still recorded.
- To investigate a failed run: click the device name in the batch detail (or the error text), read the full error on the run detail page. Common causes are connection timeouts, wrong credentials, and SSH key mismatches.
- For backup runs, the Git commit sha shown in the batch table links individual runs together. All runs in a batch share the same sha if any configs changed.
