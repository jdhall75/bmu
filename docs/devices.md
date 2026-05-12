# Devices

A device represents one physical or virtual network node that Kiroku can connect to. You can create devices one at a time or import a whole inventory from a CSV file.

## Fields

| Field | Notes |
|-------|-------|
| **Name** | A short label. Shown in lists, run results, and config history. Doesn't have to match the hostname — it's your name for the device. |
| **Hostname** | IP address or DNS name used to open the SSH/Telnet/NETCONF connection. |
| **Port** | Leave blank to use the protocol default (22 for SSH, 23 for Telnet, 830 for NETCONF). |
| **Description** | Optional notes. |
| **Groups** | Select one or more groups. Hold Ctrl/Cmd to select multiple. |
| **Platform** | How scrapli identifies the device's CLI. Built-in options cover the most common vendors; use a Custom platform for anything else. |
| **Transport** | `ssh` (default) or `telnet`. SSH is strongly preferred; Telnet is unencrypted and only useful on isolated lab networks. |
| **Driver kind** | `cli` (default) for SSH/Telnet CLI devices; `netconf` for NETCONF-capable devices. |
| **Connect timeout** | Seconds to wait for the initial connection. Blank uses the global default. Raise this for high-latency WAN links. |
| **Command timeout** | Seconds to wait for a command response. Blank uses the global default. Raise this for devices that take a long time to generate `show` output. |
| **Credential override** | Overrides the group's default credential. Leave as *(use group default)* for most devices. |
| **Enabled** | Unchecked devices are skipped by all job runs. Use this to temporarily exclude a device undergoing maintenance rather than deleting it. |

## Platform selection

**Built-in platforms** are scrapli's bundled definitions. Common options include:

- `cisco_iosxe` — Cisco IOS-XE (ASR, ISR, Catalyst 9000)
- `cisco_iosxr` — Cisco IOS-XR
- `cisco_nxos` — Cisco NX-OS
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
| `group` | Name of an existing group. A device can only be in one group via import; add it to additional groups afterwards. |
| `platform` | Built-in scrapli platform name |
| `transport` | `ssh` or `telnet` |
| `driver_kind` | `cli` or `netconf` |
| `credentials` | Name of an existing credential |
| `enabled` | `1` (default) or `0` |

Groups and credentials are matched by name — create them before running the import.

Download the **CSV template** link on the import page to get a correctly-headed example file.

## Bulk edit

On the devices list, select one or more devices with the checkboxes and click **Edit selected** to apply the same port, group membership, credential, or enabled status to all of them at once.

Note: bulk edit **adds** the selected group to each device's membership — it does not replace existing group memberships.

## Config history

After at least one successful `backup` job, the device detail page shows:

- **View Config** — the most recently captured running configuration.
- **Git History** — every version ever captured, with the ability to view any historical snapshot or compare two commits side by side.

The diff view uses a standard unified-diff presentation with green lines for additions and red for removals.

## Tips

- If you have many devices with identical settings (same platform, same group, same credential), use bulk import with a CSV — it's faster than creating them one at a time.
- Set **Enabled = false** on devices during planned maintenance rather than deleting them. Their config history and run history are preserved.
- If a device consistently fails with a timeout error, increase its **Connect timeout** and **Command timeout** individually rather than raising the global defaults for all devices.
