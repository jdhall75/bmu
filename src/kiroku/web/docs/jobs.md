# Jobs

A job defines *what* to do when it runs: which kind of operation, which commands to send, which devices or groups to target, and which parser template (if any) to use on the output. A job can be run immediately via the **Run now** button, or automated via a **Schedule**.

## Job kinds

| Kind | What it does |
|------|-------------|
| **backup** | Sends the configured commands (usually `show running-config`), captures the full output, and stores it in the Git repository. Creates a commit each time a device config changes. |
| **collect** | Sends the configured commands and optionally parses the output with a TextFSM/TTP/XSLT template. Parsed rows are stored on the run record and visible in the run detail page. |
| **cve_scan** | Like `collect`, but after parsing, it extracts a `version` field from the output and queries the NVD API for CVEs matching the device's CPE string. |

## Fields

| Field | Notes |
|-------|-------|
| **Name** | Unique label shown in the schedule list and on the dashboard. |
| **Description** | Optional. |
| **Kind** | `backup`, `collect`, or `cve_scan`. |
| **Commands** | One command per line. For `backup` jobs, typically `show running-config` (or equivalent). For `collect` and `cve_scan`, any `show` commands you want. All command output is concatenated before being passed to the parser. |
| **RPC (NETCONF)** | The raw NETCONF RPC XML to send. Only used when targeting devices with **Driver kind = netconf**. |
| **Parser template** | Applies to `collect` and `cve_scan` jobs. Without a parser template, the raw output is stored but not structured. With one, the parsed rows appear in the run detail and the ✓ badge appears in the batch table. |
| **CVE vendor** | `cve_scan` only. The vendor component of the CPE string (e.g. `cisco`). |
| **CVE product** | `cve_scan` only. The product component (e.g. `ios_xe`, `nxos`). |
| **Device groups** | The groups this job runs against. Every enabled device in every selected group is included. Hold Ctrl/Cmd to select multiple. |
| **Individual devices** | Specific devices to include regardless of their group membership. |
| **Show on device page** | `collect` jobs only. When checked, the latest successful parsed result for this job is shown on each device's detail page as a pinned panel. Useful for jobs that collect summary data like `show version` or interface status. |

## Targeting

A device is included in a job run if it appears in any of the job's **Device groups** or **Individual devices**. Duplicates (a device that appears via a group *and* individually) are deduplicated — each device runs exactly once per batch.

The credential used for a device depends on which *targeting path* brought it in:

- Device targeted via a group → group's default credential is the fallback
- Device targeted individually → system default credential is the fallback

The device's own credential override (if set) always takes precedence regardless of targeting path.

## Running a job immediately

Every row in the jobs list has a **Run now** button. This fires the job immediately without waiting for a schedule, creating a new batch. The batch appears on the dashboard and under **Runs** — click it to watch device results update in real time.

## Aggregate data view

The file-stack icon next to each `collect` or `cve_scan` job opens the **Aggregate data view** (`/jobs/{id}/data`). It shows the latest parsed result from every device in the job's scope in a single cross-device table, with one row per parsed row per device.

If the parser template has an **Aggregate report template** defined, that custom Jinja2 view is rendered instead of the plain table. See [Parsers](parsers) for template variables and examples.

## Tips

- For `backup` jobs, put `show running-config` (or `display current-configuration` for Huawei, `show configuration` for JunOS) as the single command. The entire output is committed to Git verbatim.
- For `collect` jobs, you can run multiple commands — all output is joined and passed to the parser as one string. Make sure your parser template handles the combined output correctly.
- A `collect` job without a parser template still runs successfully — the raw command output is captured and the run is marked successful, but no structured rows are stored and no ✓ badge appears in the batch table.
- If you want to test a parser before attaching it to a job, go to **Parsers → Test bed** and paste real device output there.
- `cve_scan` jobs require the parser to produce a row containing a `version` field. If the parser returns no `version` key, the CVE lookup is skipped.
