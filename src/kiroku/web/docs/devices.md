# Devices

A device represents one physical or virtual network node that Kiroku can connect to. You can create devices one at a time or import a whole inventory from a CSV file.

## Fields

| Field | Notes |
|-------|-------|
| **Name** | A short label. Shown in lists, run results, and config history. Doesn't have to match the hostname — it's your name for the device. |
| **Hostname** | IP address or DNS name used to open the SSH/Telnet/NETCONF connection. |
| **Port** | Leave blank to use the protocol default (22 for SSH, 23 for Telnet, 830 for NETCONF). |
| **Description** | Optional notes. |
| **Make** | Vendor / manufacturer (e.g. `Cisco`, `Arista`, `Juniper`). Used as a filter on the device list and in the inventory report. |
| **Model** | Hardware model string (e.g. `ASR-9000`, `Catalyst 9300`). Used in the inventory report. |
| **Role** | Functional role (e.g. `edge`, `core`, `access`). Used as a filter on the device list. |
| **Groups** | Select one or more groups. Hold Ctrl/Cmd to select multiple. |
| **Platform** | How scrapli identifies the device's CLI. Built-in options cover the most common vendors; use a Custom platform for anything else. |
| **Transport** | `ssh` (default) or `telnet`. SSH is strongly preferred; Telnet is unencrypted and only useful on isolated lab networks. |
| **Driver kind** | `cli` (default) for SSH/Telnet CLI devices; `netconf` for NETCONF-capable devices. |
| **Connect timeout** | Seconds to wait for the initial connection. Blank uses the global default. Raise this for high-latency WAN links. |
| **Command timeout** | Seconds to wait for a command response. Blank uses the global default. Raise this for devices that take a long time to generate `show` output. |
| **Credential override** | Overrides the group's default credential. Leave as *(use group default)* for most devices. |
| **Worker pool** | Routes this device's jobs to a specific worker process pool. Leave blank to use the group's pool, or the default pool if neither is set. Only relevant in multi-pool deployments. |
| **Enabled** | Unchecked devices are skipped by all job runs. Use this to temporarily exclude a device undergoing maintenance rather than deleting it. |

## Platform selection

**Built-in platforms** are scrapli's bundled definitions. Common options include:

- `cisco_iosxe` — Cisco IOS-XE (ASR, ISR, Catalyst 9000)
- `cisco_iosxr` — Cisco IOS-XR
- `cisco_nxos` — Cisco NX-OS
- `cisco_asa` — Cisco ASA
- `arista_eos` — Arista EOS
- `juniper_junos` — Juniper JunOS

**Custom platforms** are YAML definitions you write yourself (see **Platforms**). Use them for vendors not listed above, or when you need to customise prompt patterns or mode transitions.

## Bulk import

Go to **Devices → Bulk import** to upload a CSV or paste rows directly. The CSV header must include `name` and `hostname`; all other columns are optional.

| Column | Notes |
|--------|-------|
| `name` | Required |
| `hostname` | Required |
| `port` | Optional; defaults to protocol default |
| `description` | Optional |
| `make` | Optional; vendor name (e.g. `Cisco`) |
| `model` | Optional; hardware model (e.g. `ASR-9000`) |
| `role` | Optional; functional role (e.g. `edge`, `core`) |
| `group` | Name of an existing group. A device can only be in one group via import; add it to additional groups afterwards. |
| `platform` | Built-in scrapli platform name |
| `transport` | `ssh` or `telnet` |
| `driver_kind` | `cli` or `netconf` |
| `credentials` | Name of an existing credential |
| `enabled` | `1` (default) or `0` |
| `worker_pool` | Optional; worker pool name for multi-pool deployments |

Groups and credentials are matched by name — create them before running the import.

If a device with the same `name` already exists it is **updated** rather than duplicated. Fields left blank in the CSV are not cleared — only the columns you provide are applied.

Download the **CSV template** link on the import page to get a correctly-headed example file.

## Bulk edit

On the devices list, select one or more devices with the checkboxes and click **Edit selected** to apply the same port, group membership, credential, or enabled status to all of them at once.

Bulk edit fields: **Port**, **Group** (added, not replaced), **Credential**, **Enabled**, **Make**, **Model**, **Role**, and **Worker pool**. Leave a field blank to leave it unchanged. Set Credential to *"(clear override)"* to remove a device-level credential override.

## Config history

After at least one successful `backup` job, the device detail page shows:

- **View Config** — the most recently captured running configuration.
- **Git History** — every version ever captured, with the ability to view any historical snapshot or compare two commits side by side.
- **Config History Search** — search across all historical versions of this device's config. Supports plain text and regex patterns. Matches are shown with surrounding context lines and the commit timestamp where each match appears.

The diff view uses a standard unified-diff presentation with green lines for additions and red for removals.

## Inventory report

The **Inventory Report** (`/devices/report`) shows a breakdown of all devices grouped by make and model, with total count and how many have at least one backup captured. Use this to identify unmanaged device types or gaps in backup coverage.

## Tips

- If you have many devices with identical settings (same platform, same group, same credential), use bulk import with a CSV — it's faster than creating them one at a time.
- Set **Enabled = false** on devices during planned maintenance rather than deleting them. Their config history and run history are preserved.
- If a device consistently fails with a timeout error, increase its **Connect timeout** and **Command timeout** individually rather than raising the global defaults for all devices.
