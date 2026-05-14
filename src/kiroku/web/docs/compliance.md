# Compliance Policies

Compliance policies let you define rules that device configurations must satisfy. Evaluation runs entirely offline against stored backup configs — no network connection to the device is required.

The workflow is:

1. Create a policy — give it a parser and a set of checks.
2. Assign it a scope — one or more device groups and/or individual devices.
3. Run it (manually or automatically after each backup).
4. Review the results matrix: each device × check cell shows pass or fail, with drill-down to the failing rows.

---

## Parsers

A compliance policy includes its own inline parser. The parser transforms the raw backup config text into a list of dicts (rows) that the checks then evaluate.

Three parser types are available:

### `parse` (recommended for simple line matching)

The `parse` library matches one-line patterns using a format-string syntax — the inverse of Python's `str.format`. It is the easiest option when you want to extract values from specific lines without writing a full FSM template.

**Pattern syntax:** `{FIELD}` captures everything to the end of the line. `{FIELD:S}` captures a single non-whitespace word. `{FIELD:d}` captures an integer.

```
ntp server {NTP_SERVER}
```

Applied to a config containing:
```
ntp server 10.0.0.1
ntp server 10.0.0.2
```

Produces:
```json
[
  {"NTP_SERVER": "10.0.0.1"},
  {"NTP_SERVER": "10.0.0.2"}
]
```

Each matching line becomes one row. Lines that don't match the pattern are skipped.

**More examples:**

```
hostname {HOSTNAME}
```
```
ip route {NETWORK} {MASK} {NEXTHOP}
```
```
username {USERNAME:S} privilege {PRIV:d} secret {SECRET}
```
```
snmp-server community {COMMUNITY:S} {ACCESS:S}
```

**`parse` type specifiers:**

| Specifier | Matches |
|-----------|---------|
| `{FIELD}` | Rest of the line (greedy to end) |
| `{FIELD:S}` | One non-whitespace word |
| `{FIELD:d}` | Integer |
| `{FIELD:f}` | Float |
| `{FIELD:w}` | Letters, digits, and `_` |
| `{FIELD:x}` | Hexadecimal |

The pattern is searched within each line (not anchored to the start), so `ntp server {NTP_SERVER}` also matches `  ntp server 10.0.0.1` (indented). To require the pattern to match the full line exactly, include all leading/trailing content in the pattern.

### `textfsm`

TextFSM uses a template language with `Value` declarations and `State` machines. Use it when the output has predictable columns, multiple values per line, or needs state tracking across lines (e.g. interface blocks).

```
Value NTP_SERVER (\S+)
Value NTP_STATUS (\S+)

Start
  ^ntp server ${NTP_SERVER} -> Record
```

See the [Parsers](parsers) help page for full TextFSM documentation and examples.

### `ttp`

TTP (Template Text Parser) handles free-form or nested output using Jinja-like template syntax.

```
<group name="ntp">
ntp server {{ NTP_SERVER }}
</group>
```

See the [Parsers](parsers) help page for TTP documentation.

---

## Checks

Each check tests a condition against the parsed rows. A policy can have any number of checks; each check is evaluated independently.

### Check fields

| Field | Description |
|-------|-------------|
| **Name** | Short label shown in the results matrix (e.g. "NTP server present") |
| **Field** | Key in the parsed row dict (e.g. `NTP_SERVER`) — case-sensitive, must match the parser output exactly |
| **Operator** | How to compare the field value against the expected value |
| **Expected** | The value to compare against (not used for `exists` / `not_exists`) |
| **Mode** | How many rows must satisfy the condition for the check to pass |
| **Severity** | `critical`, `major`, `minor`, or `info` — controls overall policy status |
| **Description** | Message shown in failure detail (e.g. "All NTP servers must be in the approved list") |

### Operators

| Operator | Passes when… |
|----------|-------------|
| `eq` | `field == expected` (numeric-aware: `"10" eq "10.0"` passes) |
| `ne` | `field != expected` |
| `contains` | `expected` is a substring of `field` (case-insensitive) |
| `not_contains` | `expected` is not a substring of `field` |
| `regex` | `field` matches the regex `expected` (case-insensitive POSIX ERE) |
| `gt` | `float(field) > float(expected)` |
| `lt` | `float(field) < float(expected)` |
| `ge` | `float(field) >= float(expected)` |
| `le` | `float(field) <= float(expected)` |
| `exists` | `field` is present and non-empty in the row |
| `not_exists` | `field` is absent or empty in the row |

### Mode

| Mode | Passes when… |
|------|-------------|
| `any` | At least one parsed row satisfies the condition |
| `all` | Every parsed row satisfies the condition |
| `none` | No parsed rows satisfy the condition (inverse existence check) |

**Choosing the right mode:**

- Use `any` to assert that something exists: "at least one NTP server is configured."
- Use `all` to assert a universal property: "every BGP neighbor is in state Established."
- Use `none` to assert something is absent: "no Telnet lines are configured."

### Severity

- **`critical`** / **`major`**: failing check sets the overall device result to `fail`.
- **`minor`**: failing check is flagged but does not affect the overall `pass`/`fail` status.
- **`info`**: recorded in the detail for visibility only; never causes a fail.

---

## Overall device status

| Status | Meaning |
|--------|---------|
| `pass` | All critical and major checks passed |
| `fail` | At least one critical or major check failed |
| `error` | The parser threw an exception — check your parser body |
| `skip` | No stored backup config for this device |

---

## Complete examples

### Example 1 — NTP servers must be in the approved list

**Parser type:** `parse`

**Parser body:**
```
ntp server {NTP_SERVER}
```

**Checks:**

| Name | Field | Operator | Expected | Mode | Severity |
|------|-------|----------|----------|------|----------|
| Approved NTP 1 | NTP_SERVER | contains | 10.0.0.1 | any | major |
| No public NTP | NTP_SERVER | not_contains | pool.ntp.org | none | major |

The first check passes if any row has an NTP_SERVER containing `10.0.0.1`.
The second check passes if no row has an NTP_SERVER containing `pool.ntp.org`.

---

### Example 2 — Minimum IOS version

**Parser type:** `textfsm`

**Parser body:**
```
Value VERSION (\S+)

Start
  ^Cisco IOS.*Version\s+${VERSION}, -> Record
```

**Check:**

| Name | Field | Operator | Expected | Mode | Severity |
|------|-------|----------|----------|------|----------|
| IOS version ≥ 15.6 | VERSION | ge | 15.6 | any | critical |

---

### Example 3 — No Telnet VTY lines

**Parser type:** `parse`

**Parser body:**
```
 transport input {TRANSPORT}
```

**Check:**

| Name | Field | Operator | Expected | Mode | Severity |
|------|-------|----------|----------|------|----------|
| No Telnet | TRANSPORT | contains | telnet | none | critical |

Passes if no line matches `transport input telnet` (or `transport input all`).

---

### Example 4 — BGP neighbor states

**Parser type:** `textfsm` (from ntc-templates `cisco_ios_show_bgp_summary`)

**Check:**

| Name | Field | Operator | Expected | Mode | Severity |
|------|-------|----------|----------|------|----------|
| All BGP neighbors up | STATE_PFXRCD | regex | ^\d+$ | all | major |

The `ntc-templates` BGP summary parser uses a numeric prefix count when a neighbor is established; non-established states are strings. This regex checks that every neighbor row has a numeric value (i.e. is established).

---

## Auto-evaluate after backup

When **Auto-evaluate after backup** is enabled on a policy, Kiroku re-evaluates the policy automatically when a backup batch finishes for any device in the policy's scope. Results are updated immediately — no manual run is required.

This is the recommended setting for compliance policies that track configuration drift. Disable it for policies you only want to run on demand.

---

## Scope

A policy applies to the union of all selected device groups and individual devices. If a device appears in both a selected group and the individual list, it is evaluated once.

Devices with no stored backup show a `skip` result. Run a backup job first to populate their config.

---

## Tips

- Start with the **parse** type for simple checks. Switch to TextFSM if you need multi-value per line or state-based matching.
- Test your parser body in the [Parser test bed](/parsers/test) — paste the device config in the left pane and your template on the right. The test bed supports TextFSM, TTP, and the `parse` type.
- Use **mode = `any`** to check existence, **`all`** for universal properties, **`none`** for prohibited values.
- Set severity to **`info`** for informational checks you want to track but not fail on — useful for gradually rolling out a new standard.
- The results matrix updates each time you click **Run now** (or after each backup if auto-evaluate is on). Historic results are not retained — only the latest result per device is kept.
