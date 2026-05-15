# Groups

A group is a named collection of devices. Groups serve three purposes:

1. **Credential scope** — a group carries a default credential that all its member devices inherit unless they have their own override.
2. **Job targeting** — a job can be assigned to one or more groups, which means it will run against every enabled device in those groups.
3. **Concurrency control** — the **Max parallel** setting limits how many devices in the group are worked at the same time during a job run.

## Fields

| Field | Notes |
|-------|-------|
| **Name** | Unique identifier. Used in job targeting, the devices list, and search filters. |
| **Description** | Optional free text. |
| **Default credential** | The credential all member devices inherit if they don't have their own override. Leave blank only if every device in the group will have its own credential. |
| **Max parallel** | Maximum number of concurrent device connections during a job run. Defaults to 8. Lower this on production networks where opening many SSH sessions simultaneously could trigger rate-limits or CPU spikes on core devices. |
| **Worker pool** | Routes all devices in this group to a specific worker process pool. Leave blank to use the default pool. A device-level worker pool override takes precedence over the group setting. Only relevant in multi-pool deployments where different pools connect to different network segments. |

## Many-to-many membership

A device can belong to multiple groups simultaneously. This is useful when you have overlapping job definitions:

- A device might be in a `backup-core` group (targeted by a nightly backup job) *and* a `version-scan` group (targeted by a weekly CVE scan job).
- The credential used for a run is determined by which group was the *targeting* group for that particular job, not by the first group the device belongs to.

## Group detail page

The group detail page shows:

- **Schedules** — schedules linked to this group via jobs that target it.
- **Devices** — all member devices with their hostname, platform, and enabled status.

Click a device name to go directly to the device detail page.

## Tips

- Start with broad groups (by site or by vendor) and add narrower groups later if you need different job schedules or credentials for a subset of devices.
- If you want to run a one-off job against a subset of devices without changing the permanent group structure, create a temporary group, run the job, then delete the group.
- Deleting a group does **not** delete its member devices. The many-to-many relationship is severed, but the devices remain.
