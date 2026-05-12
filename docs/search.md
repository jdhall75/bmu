# Config Search

The Search page queries the text of all backed-up device configurations stored in the database. Only configurations captured by a `backup` job appear here — it does not search `collect` job output.

## Search modes

### Full-text (keywords)

Uses PostgreSQL full-text search with the `simple` dictionary. Best for:

- Keywords that may appear in inflected forms
- Searching across many devices quickly
- General-purpose exploration ("find all devices with OSPF configured")

Full-text search does not preserve word boundaries for short tokens — searching `bgp` will match `bgp`, `ibgp`, `ebgp` etc.

### Exact match

Uses `LIKE '%term%'` pattern matching. Best for:

- IP addresses: `192.168.1.254`
- Interface names: `GigabitEthernet0/0/1`
- Exact strings that must appear verbatim in the config

Exact match is case-insensitive but otherwise literal — it won't match partial words or stemmed forms.

## Filters

| Filter | Notes |
|--------|-------|
| **Group** | Limit results to devices in a specific group. Useful when you manage multiple sites and want to scope the search. |
| **Context lines** | How many lines of surrounding config to show above and below each match. Default is 2. Set to 0 for match-only display; raise to 5–10 for more context when investigating complex configurations. |

## Reading results

Each matching device shows:

- Device name (links to the device detail page)
- Group membership
- When the config was last captured
- **View config** button to see the full configuration
- Highlighted snippets showing the matching lines in context

Lines that contain the search term are highlighted in yellow. Surrounding context lines are shown in the usual dark-background monospace style.

## What gets indexed

Only configurations stored by `backup` jobs are searchable. The full-text index (`device_configs.content_fts`) is updated each time a new backup is captured. The most recent config per device is indexed — historical versions visible in Git history are not searchable (use the config history and diff views to inspect older snapshots).

## Tips

- Use **Exact** mode for IP addresses — full-text search strips punctuation and would not find `10.0.0.1` reliably.
- Use the **Group** filter when you have many devices and expect the term to appear in many places. For example, searching `ntp server` across a large fleet is more useful when scoped to a site.
- If a device does not appear in search results even though it should have a backup, check its **Device detail → Recent runs** to confirm the last backup run succeeded. Configs are only indexed on successful runs.
- The result list is capped at 50 devices. If you get exactly 50 results, your query is too broad — add more terms or apply a group filter to narrow it.
