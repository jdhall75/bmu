# Schedules

A schedule attaches a job to a recurring cron expression, so the job runs automatically at the configured times without manual intervention.

## Fields

| Field | Notes |
|-------|-------|
| **Name** | A descriptive label shown in the schedule list and in run history. Good names describe *what* and *when*: `nightly-backup-core`, `weekly-cve-edge`. |
| **Description** | Optional. |
| **Job** | The job to run. A single job can be attached to multiple schedules (e.g. run backup hourly during business hours and nightly otherwise). |
| **Cron expression** | Standard 5-field cron: `minute hour day-of-month month day-of-week`. See examples below. |
| **Timezone** | An IANA timezone name. Defaults to `UTC`. Use your local timezone if you want runs to align with business hours. |
| **Enabled** | Uncheck to pause the schedule without deleting it. |

## Cron expression examples

| Expression | Meaning |
|-----------|---------|
| `0 3 * * *` | Every day at 03:00 |
| `0 2 * * 0` | Every Sunday at 02:00 |
| `30 6 * * 1-5` | Weekdays at 06:30 |
| `0 */4 * * *` | Every 4 hours |
| `0 8,20 * * *` | 08:00 and 20:00 daily |

## Timezone

Specify an IANA timezone name, not an offset like `+05:30`. Examples:

- `UTC`
- `America/New_York`
- `America/Chicago`
- `America/Los_Angeles`
- `Europe/London`
- `Europe/Paris`
- `Asia/Tokyo`
- `Australia/Sydney`

The **Next run** column on the schedule list shows the upcoming execution time in the configured timezone.

## How scheduling works

The Kiroku scheduler process reads all enabled schedules on startup and builds an in-memory priority queue. At each tick it checks whether any schedule is due, fires `fire_job()` for each one, and recalculates the next run time using `croniter`. If the scheduler process is restarted, the next run time is recalculated from the current time — jobs are not replayed for missed ticks.

## Tips

- Stagger backup schedules across sites to avoid all devices connecting simultaneously. For example, use `0 2 * * *` for Site A and `0 3 * * *` for Site B.
- Run CVE scans less frequently than config backups — once a week or once a month is usually sufficient. New CVEs appear in the NVD database with a delay anyway.
- If you want to run a job immediately, use the **Run now** button on the job list — you don't need to create a schedule for ad-hoc runs.
- Disable a schedule temporarily during a network maintenance window to avoid generating a flood of failure records. Re-enable it when the window closes.
