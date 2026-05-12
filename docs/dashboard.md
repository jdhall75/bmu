# Dashboard

The dashboard gives a live snapshot of the system and a feed of recent job activity.

## Summary cards

| Card | What it counts |
|------|---------------|
| **Groups** | Total device groups defined |
| **Devices** | Total devices (enabled and disabled) |
| **Schedules** | Total schedules (enabled and disabled) |
| **Jobs Executed** | Total batch runs ever recorded |

The **Jobs Executed** card shows an all-time count, not just recent runs. If any batch run ever contained failures it contributes to the red "with failures" note below the count — this is cumulative and expected to grow over time as you run jobs on unreachable devices.

## Recent jobs table

Shows the last 20 batch runs, newest first.

- **Job** — links to the batch detail page where you can see per-device results.
- **Finished** — shows a yellow "running" badge if the batch is still in progress. The page uses HTMx live polling so running rows update automatically every few seconds without a manual refresh.
- **Commit** — the first 8 characters of the Git commit sha created when a `backup` job completes. Clicking into the batch then into an individual run shows the full sha.

## Workflow link

Click **Getting Started** (the `?` icon in the header) for a step-by-step setup guide showing the correct order to create resources.

## Tips

- If a job shows failures, click its name to open the batch detail. Failed device rows are highlighted red and link to the individual run which shows the full error message.
- Batches that ran while no devices were reachable (e.g. during a maintenance window) will show as fully failed. This is normal and does not affect future runs.
- If a batch appears stuck in "running" indefinitely, the recorder's stale-batch reaper will force-close it after the configured timeout (default 30 minutes) and mark any incomplete runs as failed.
