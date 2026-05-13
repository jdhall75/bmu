# Parser Templates

Parser templates transform raw CLI or NETCONF output into structured data. Once attached to a `collect` or `cve_scan` job, the parsed rows are stored on each run record and displayed in the run detail page as a table (or JSON for non-tabular output).

## Parser types

| Type | Best for | Output |
|------|----------|--------|
| **TextFSM** | CLI output with consistent column formatting (routing tables, interface lists, ARP tables) | List of dicts |
| **TTP** | CLI output with more free-form or nested structure | List of dicts (or nested) |
| **XSLT** | NETCONF XML responses | Dict with a `transformed` key |

### TextFSM

TextFSM uses a template language with `Value` declarations and `State` machines. It is best when the output has predictable columns and row delimiters.

```
Value HOSTNAME (\S+)
Value VERSION (\S+)

Start
  ^${HOSTNAME}\s+version\s+${VERSION} -> Record
```

Each `Record` action captures one row. The result is a list of dicts with keys matching the `Value` names.

TextFSM templates are community-maintained in the [ntc-templates](https://github.com/networktocode/ntc-templates) repository — you can copy templates from there and paste them into the template body.

### TTP

TTP (Template Text Parser) is more flexible than TextFSM for output that doesn't follow rigid column alignment. It uses a Jinja-like template syntax.

```
<group name="interfaces">
Interface {{ interface }} is {{ admin_status }}, line protocol is {{ line_status }}
</group>
```

The result is a list of groups (dicts), one per matched block.

### XSLT

XSLT is used to transform XML output from NETCONF RPCs. The result is always a single dict with a `transformed` key containing the string output of the stylesheet.

## Test bed

The **Test bed** (`/parsers/test`) lets you iterate on a parser template without running a real job:

1. Paste real device output in the **Device output** pane (left)
2. Paste or type your template in the **Parser template** pane (right)
3. Click **Run** (or press **Ctrl+Enter / Cmd+Enter**)
4. The **Result** pane shows the parsed JSON

You can load any saved template from the **Load saved template** dropdown. After loading, it sets both the type selector and the template body — you can then modify the template and test without saving.

If the result shows an error, the pane turns red and shows the exception message, which usually pinpoints the syntax problem.

## Output template (Jinja2)

After a collect run, Kiroku stores the parsed rows and displays them as a plain key/value table by default. If you want a custom layout — grouping fields, hiding columns, adding labels, or formatting values — add a **Jinja2 output template** to the parser.

The template is rendered once per device run and shown on the **Run detail** page and on the **Device detail** page in the "Collected data" section.

### Variables available inside the template

| Variable | Type | Description |
|----------|------|-------------|
| `rows` | `list[dict]` | Every parsed row. Always a list, even for single-row output. |
| `headers` | `list[str]` | The keys from the first row (column names). |
| `data` | same as `rows` | Alias for `rows`. Use whichever reads more naturally. |

`rows` is always a list. For output that produces a single logical record (e.g. `show version`), it still comes in as a one-element list — use `rows[0]` to access it directly.

**What `rows` looks like for a TextFSM parser:**

```json
[
  {"INTERFACE": "GigabitEthernet0/0", "STATUS": "up",   "PROTOCOL": "up"},
  {"INTERFACE": "GigabitEthernet0/1", "STATUS": "down", "PROTOCOL": "down"},
  {"INTERFACE": "Loopback0",          "STATUS": "up",   "PROTOCOL": "up"}
]
```

**What `rows` looks like for a TTP parser** (group output, single element):

```json
[
  {
    "hostname": "core-sw-01",
    "version": "16.9.4",
    "interfaces": [
      {"name": "Gi0/0", "ip": "10.0.0.1", "mask": "255.255.255.0"},
      {"name": "Gi0/1", "ip": "10.0.1.1", "mask": "255.255.255.0"}
    ]
  }
]
```

**What `rows` looks like for an XSLT parser:**

XSLT always produces a single dict with a `transformed` key:

```json
[{"transformed": "<interfaces><interface>...</interface></interfaces>"}]
```

### Jinja2 syntax quick reference

Templates use standard Jinja2 syntax:

| Construct | Syntax | Purpose |
|-----------|--------|---------|
| Expression | `{{ value }}` | Output a value |
| Statement | `{% ... %}` | Control flow, assignment |
| Comment | `{# ... #}` | Not rendered in output |
| Variable access | `{{ r.FIELD }}` or `{{ r['FIELD'] }}` | Dict field access |
| Safe default | `{{ r.get('FIELD', '-') }}` | Missing key fallback |
| Filter | `{{ value \| filter }}` | Transform a value |
| Chained filters | `{{ value \| filter1 \| filter2 }}` | Apply multiple transforms |

**Control flow:**

```jinja2
{% for r in rows %}
  ...
{% endfor %}

{% if condition %}
  ...
{% elif other_condition %}
  ...
{% else %}
  ...
{% endif %}

{% set my_var = rows | selectattr('STATUS', 'eq', 'up') | list %}
```

**Loop variables** (`loop.*` inside a `{% for %}` block):

| Variable | Value |
|----------|-------|
| `loop.index` | Current iteration (1-based) |
| `loop.index0` | Current iteration (0-based) |
| `loop.first` | `True` on the first iteration |
| `loop.last` | `True` on the last iteration |
| `loop.length` | Total number of iterations |

### Available Jinja2 filters

The template runs in a **sandboxed Jinja2 environment**. Arbitrary Python execution is blocked, but the following standard filters all work:

**String filters:**

| Filter | Example | Result |
|--------|---------|--------|
| `upper` | `{{ r.NAME \| upper }}` | `"CORE-SW-01"` |
| `lower` | `{{ r.NAME \| lower }}` | `"core-sw-01"` |
| `title` | `{{ r.NAME \| title }}` | `"Core-Sw-01"` |
| `trim` | `{{ r.NAME \| trim }}` | Leading/trailing whitespace removed |
| `replace` | `{{ r.NAME \| replace('-', '_') }}` | `"core_sw_01"` |
| `truncate` | `{{ r.DESC \| truncate(40) }}` | Truncates at 40 chars with `…` |

**Number filters:**

| Filter | Example | Result |
|--------|---------|--------|
| `int` | `{{ r.COUNT \| int }}` | Cast to integer |
| `float` | `{{ r.RATE \| float }}` | Cast to float |
| `round` | `{{ r.RATE \| float \| round(2) }}` | Round to 2 decimal places |

**List filters:**

| Filter | Example | Result |
|--------|---------|--------|
| `length` | `{{ rows \| length }}` | Count of items |
| `first` | `{{ rows \| first }}` | First element |
| `last` | `{{ rows \| last }}` | Last element |
| `sort` | `{{ rows \| sort(attribute='INTERFACE') }}` | Sort by field |
| `reverse` | `{{ rows \| reverse \| list }}` | Reverse order |
| `join` | `{{ items \| join(', ') }}` | Join list into string |
| `map` | `{{ rows \| map(attribute='NAME') \| list }}` | Extract one field from each row |
| `unique` | `{{ rows \| map(attribute='VRF') \| unique \| list }}` | Deduplicated values |
| `selectattr` | `{{ rows \| selectattr('STATUS', 'eq', 'up') \| list }}` | Filter by attribute value |
| `rejectattr` | `{{ rows \| rejectattr('STATUS', 'eq', 'up') \| list }}` | Exclude by attribute value |
| `groupby` | `{% for key, group in rows \| groupby('VRF') %}` | Group rows by a field |

**`selectattr` / `rejectattr` operators:**

| Operator | Meaning |
|----------|---------|
| `eq` | Equal to |
| `ne` | Not equal to |
| `lt` | Less than |
| `le` | Less than or equal |
| `gt` | Greater than |
| `ge` | Greater than or equal |
| `defined` | Attribute exists |
| `undefined` | Attribute does not exist |

### Kiroku CSS classes

Use these classes to match the rest of the UI:

| Class | Element | Use |
|-------|---------|-----|
| `table-wrap` | `<div>` | Wraps a `<table>` for horizontal scroll on narrow screens |
| `detail-grid` | `<dl>` | Two-column key/value grid using `<dt>` and `<dd>` |
| `status` | `<span>` | Base class for status pills — always combine with a variant |
| `status-success` | `<span>` | Green pill — up / ok / success |
| `status-failed` | `<span>` | Red pill — down / error / failed |
| `status-running` | `<span>` | Yellow pill — in progress |
| `muted` | any | Lighter, de-emphasized text |
| `error-block` | `<pre>` | Red-bordered error message block |
| `parsed-output` | `<div>` | Container for custom parsed output (adds consistent spacing) |

### Examples

**Simple table with custom column order** — `show chassis hardware` (Juniper):

```jinja2
<div class="table-wrap">
<table>
  <thead>
    <tr><th>Name</th><th>Description</th><th>Part Number</th><th>Serial</th></tr>
  </thead>
  <tbody>
    {% for r in rows %}
    <tr>
      <td>{{ r.NAME }}</td>
      <td>{{ r.DESCR }}</td>
      <td><code>{{ r.PID }}</code></td>
      <td><code>{{ r.SN }}</code></td>
    </tr>
    {% endfor %}
  </tbody>
</table>
</div>
```

**Summary card** — single-row output like `show version`:

```jinja2
{% set r = rows[0] %}
<dl class="detail-grid">
  <dt>Hostname</dt><dd>{{ r.HOSTNAME }}</dd>
  <dt>Version</dt><dd>{{ r.VERSION }}</dd>
  <dt>Uptime</dt><dd>{{ r.UPTIME }}</dd>
  <dt>Platform</dt><dd>{{ r.PLATFORM }}</dd>
  <dt>Serial</dt><dd><code>{{ r.SERIAL }}</code></dd>
</dl>
```

**Conditional formatting** — colour-code a status field:

```jinja2
<div class="table-wrap">
<table>
  <thead><tr><th>Interface</th><th>Status</th><th>Protocol</th><th>IP Address</th></tr></thead>
  <tbody>
  {% for r in rows %}
    <tr>
      <td>{{ r.INTERFACE }}</td>
      <td>
        {% if r.STATUS == 'up' %}
          <span class="status status-success">up</span>
        {% else %}
          <span class="status status-failed">{{ r.STATUS }}</span>
        {% endif %}
      </td>
      <td>
        {% if r.PROTOCOL == 'up' %}
          <span class="status status-success">up</span>
        {% else %}
          <span class="status status-failed">{{ r.PROTOCOL }}</span>
        {% endif %}
      </td>
      <td><code>{{ r.IP | default('-') }}</code></td>
    </tr>
  {% endfor %}
  </tbody>
</table>
</div>
```

**Filter rows** — show only down interfaces, with a summary line:

```jinja2
{% set up   = rows | selectattr('STATUS', 'eq', 'up') | list %}
{% set down = rows | rejectattr('STATUS', 'eq', 'up') | list %}

<p>
  <span class="status status-success">{{ up | length }} up</span>
  <span class="status status-failed">{{ down | length }} down</span>
  of {{ rows | length }} interfaces
</p>

{% if down %}
<div class="table-wrap">
<table>
  <thead><tr><th>Interface</th><th>Status</th><th>Protocol</th></tr></thead>
  <tbody>
  {% for r in down %}
    <tr>
      <td>{{ r.INTERFACE }}</td>
      <td><span class="status status-failed">{{ r.STATUS }}</span></td>
      <td><span class="status status-failed">{{ r.PROTOCOL }}</span></td>
    </tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% else %}
<p class="muted">All interfaces are up.</p>
{% endif %}
```

**Group rows by a field** — BGP neighbors grouped by VRF:

```jinja2
{% for vrf, neighbors in rows | groupby('VRF') %}
<h4>VRF: {{ vrf or 'default' }}</h4>
<div class="table-wrap">
<table>
  <thead><tr><th>Neighbor</th><th>AS</th><th>State</th><th>Prefixes</th></tr></thead>
  <tbody>
  {% for r in neighbors %}
    <tr>
      <td><code>{{ r.NEIGHBOR }}</code></td>
      <td>{{ r.REMOTE_AS }}</td>
      <td>
        {% if r.STATE == 'Established' %}
          <span class="status status-success">{{ r.STATE }}</span>
        {% else %}
          <span class="status status-failed">{{ r.STATE }}</span>
        {% endif %}
      </td>
      <td>{{ r.PREFIXES | default('0') }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% endfor %}
```

**Sort a table** — route table sorted by prefix length:

```jinja2
<div class="table-wrap">
<table>
  <thead><tr><th>Network</th><th>Mask</th><th>Next Hop</th><th>Protocol</th></tr></thead>
  <tbody>
  {% for r in rows | sort(attribute='NETWORK') %}
    <tr>
      <td><code>{{ r.NETWORK }}</code></td>
      <td><code>{{ r.MASK }}</code></td>
      <td><code>{{ r.NEXTHOP }}</code></td>
      <td>{{ r.PROTOCOL }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
</div>
```

**Extract a list from rows** — unique VLANs as a compact pill list:

```jinja2
{% set active = rows | selectattr('STATE', 'eq', 'active') | list %}
{% set vlans = active | map(attribute='VLAN_ID') | list %}
<p><strong>{{ vlans | length }} active VLAN(s):</strong></p>
<p>
{% for v in vlans | sort %}
  <code>{{ v }}</code>{% if not loop.last %}, {% endif %}
{% endfor %}
</p>
```

**Two-section layout** — split hardware into chassis vs. line cards:

```jinja2
{% set chassis = rows | selectattr('TYPE', 'eq', 'Chassis') | list %}
{% set modules = rows | rejectattr('TYPE', 'eq', 'Chassis') | list %}

{% if chassis %}
<h4>Chassis</h4>
<dl class="detail-grid">
  {% for r in chassis %}
  <dt>{{ r.NAME }}</dt><dd>{{ r.DESCR }} — <code>{{ r.SN }}</code></dd>
  {% endfor %}
</dl>
{% endif %}

{% if modules %}
<h4>Modules / Line Cards</h4>
<div class="table-wrap">
<table>
  <thead><tr><th>Slot</th><th>Description</th><th>Part</th><th>Serial</th></tr></thead>
  <tbody>
  {% for r in modules %}
    <tr>
      <td>{{ r.NAME }}</td>
      <td>{{ r.DESCR }}</td>
      <td><code>{{ r.PID }}</code></td>
      <td><code>{{ r.SN }}</code></td>
    </tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% endif %}
```

**TTP nested output** — iterating sub-lists from a TTP group:

TTP parsers can produce nested structures. Access sub-lists the same way — they are just dicts within dicts.

```jinja2
{# rows[0] is the top-level group; rows[0].interfaces is the nested list #}
{% set r = rows[0] %}
<dl class="detail-grid">
  <dt>Hostname</dt><dd>{{ r.hostname }}</dd>
  <dt>Version</dt><dd>{{ r.version }}</dd>
</dl>

<h4>Interfaces</h4>
<div class="table-wrap">
<table>
  <thead><tr><th>Interface</th><th>IP Address</th><th>Mask</th></tr></thead>
  <tbody>
  {% for iface in r.interfaces | default([]) %}
    <tr>
      <td>{{ iface.name }}</td>
      <td><code>{{ iface.ip }}</code></td>
      <td><code>{{ iface.mask }}</code></td>
    </tr>
  {% endfor %}
  </tbody>
</table>
</div>
```

**Guard for empty output** — always handle the case where `rows` is empty:

```jinja2
{% if not rows %}
<p class="muted">No data collected for this run.</p>
{% else %}
<div class="table-wrap">
<table>
  <thead><tr>{% for h in headers %}<th>{{ h }}</th>{% endfor %}</tr></thead>
  <tbody>
  {% for r in rows %}
    <tr>{% for h in headers %}<td>{{ r.get(h, '') }}</td>{% endfor %}</tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% endif %}
```

### Debugging tips

- **Use the test bed first.** The test bed at `/parsers/test` shows template errors instantly without running a real job. Paste your device output and iterate there.
- **Read the error message carefully.** If the template fails, the run detail page shows a red **Template error** block with the Jinja2 exception. The line number in the error refers to the template, not the page.
- **Common mistake — accessing a missing key directly:** `{{ r.FIELD }}` raises `UndefinedError` if `FIELD` is not present in the dict. Use `{{ r.get('FIELD', '') }}` or `{{ r.FIELD | default('') }}` as a safe fallback.
- **Common mistake — treating `rows` as a single dict:** TTP and TextFSM both return a list. Even if there is only one record, use `rows[0].FIELD`, not `rows.FIELD`.
- **Common mistake — forgetting `| list` after a filter:** `selectattr` and `groupby` return iterators. Chain `| list` before passing to `| length` or indexing: `{{ rows | selectattr('STATUS', 'eq', 'up') | list | length }}`.
- **Blank template:** If you leave the output template empty, Kiroku shows the default auto-generated table. This is a safe fallback while developing.
- **Check the parser output first:** If the template looks correct but the output is wrong, run the parser in the test bed and inspect the raw `rows` JSON to confirm the field names and structure match your template.

### Notes

- The template runs in a **sandboxed Jinja2 environment** — standard filters work, but arbitrary Python execution (calling functions, importing modules) is blocked.
- If the template raises an error, a red **Template error** block is shown on the run detail page with the exception message. The default table is not shown as a fallback — fix the template and re-run the job.
- Leave the field blank to keep the default auto-generated table.
- You can use Kiroku's CSS classes (`detail-grid`, `table-wrap`, `status`, `status-success`, `status-failed`, `status-running`, `muted`) to make the output match the rest of the UI.

## Aggregate report template (Jinja2)

The **aggregate report template** renders the collected data from **all devices** for a job in a single view, accessible via the file-multiple icon on the Jobs list. Where the output template (above) renders one device's run result, the aggregate template receives every device's data together.

If no aggregate template is set, Kiroku shows a plain fill-down table with the device name in the first column and one row per parsed row per device.

### Variables available inside the template

| Variable | Type | Description |
|----------|------|-------------|
| `rows` | `list[dict]` | Flat list of all parsed rows across all devices. Each dict has a `"device"` key (the device name) prepended, followed by the parser's field keys. |
| `headers` | `list[str]` | Ordered list of parser field names (excludes `"device"`). Built from the union of all field keys seen across all devices. |
| `devices` | `list[dict]` | One entry per device in job scope. Each dict has `name` (str), `id` (int), `collected_at` (datetime or None), and `rows` (list of field dicts, same as parsed_data but without the `"device"` key). |
| `job` | `Job` | The job ORM object. Useful for `job.name`, `job.description`, etc. |

Devices with no collected data appear in `devices` with `rows = []` and `collected_at = None`. They also appear in `rows` with no entries (so they are effectively skipped in a flat iteration over `rows`).

### Examples

**Flat table with all devices** — replicates the default view with custom column selection:

```jinja2
<div class="table-wrap">
<table>
  <thead>
    <tr>
      <th>Device</th>
      {% for h in headers %}<th>{{ h }}</th>{% endfor %}
    </tr>
  </thead>
  <tbody>
    {% for r in rows %}
    <tr>
      <td>{{ r.device }}</td>
      {% for h in headers %}<td>{{ r.get(h, '') }}</td>{% endfor %}
    </tr>
    {% endfor %}
  </tbody>
</table>
</div>
```

**Per-device summary cards** — one card per device showing selected fields:

```jinja2
{% for d in devices %}
<h3>{{ d.name }}</h3>
{% if d.rows %}
  <dl class="detail-grid">
    <dt>Version</dt><dd>{{ d.rows[0].get('VERSION', '-') }}</dd>
    <dt>Uptime</dt><dd>{{ d.rows[0].get('UPTIME', '-') }}</dd>
    <dt>Collected</dt><dd>{{ d.collected_at.strftime('%Y-%m-%d %H:%M') if d.collected_at else '-' }}</dd>
  </dl>
{% else %}
  <p class="muted">No data collected.</p>
{% endif %}
{% endfor %}
```

**Cross-device status overview** — show all devices with a field grouped by status value:

```jinja2
{% set up_rows   = rows | selectattr('STATUS', 'eq', 'up')   | list %}
{% set down_rows = rows | selectattr('STATUS', 'ne', 'up')   | list %}

<p>
  <span class="status status-success">{{ up_rows | length }} up</span>
  <span class="status status-failed">{{ down_rows | length }} down</span>
  across {{ devices | length }} device(s)
</p>

{% if down_rows %}
<h3>Down interfaces</h3>
<div class="table-wrap">
<table>
  <thead><tr><th>Device</th><th>Interface</th><th>Status</th></tr></thead>
  <tbody>
    {% for r in down_rows %}
    <tr>
      <td>{{ r.device }}</td>
      <td>{{ r.INTERFACE }}</td>
      <td><span class="status status-failed">{{ r.STATUS }}</span></td>
    </tr>
    {% endfor %}
  </tbody>
</table>
</div>
{% endif %}
```

**Device × field pivot** — compare one field across all devices:

```jinja2
<div class="table-wrap">
<table>
  <thead><tr><th>Device</th><th>Version</th><th>Platform</th></tr></thead>
  <tbody>
    {% for d in devices %}
    <tr>
      <td>{{ d.name }}</td>
      <td>{{ d.rows[0].get('VERSION', '-') if d.rows else '-' }}</td>
      <td>{{ d.rows[0].get('PLATFORM', '-') if d.rows else '-' }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
</div>
```

### CSV download

Add a `data-csv="filename.csv"` attribute to any `<table>` in your aggregate template and a **↓ Download CSV** link is automatically injected above it at page load — no JavaScript needed in the template itself.

```jinja2
<table data-csv="{{ job.name }}-bgp-neighbors.csv">
  ...
</table>

<table data-csv="{{ job.name }}-interfaces.csv">
  ...
</table>
```

Each table gets its own independent download link. The filename is whatever string you pass to `data-csv`.

### Notes

- The aggregate template uses the same **sandboxed Jinja2 environment** as the output template — standard filters work, arbitrary Python execution is blocked.
- If the template raises an error, a red error block is shown at the top of the page and the default fill-down table is rendered below it, so data remains visible while you debug the template.
- Leave the field blank to keep the default cross-device table.
- Use the same Kiroku CSS classes (`detail-grid`, `table-wrap`, `status`, `status-success`, `status-failed`, `muted`) to match the UI.
- The `rows` list only contains rows from devices that produced data. Devices with no data do not appear in `rows` — check `devices` and test `d.rows` to handle them explicitly.
- Data comes from the **latest successful run** per device for this job. Older runs are not included.

## Saving and using a template

1. Click **New parser template** or open an existing one via **Edit**.
2. Paste the template body and choose the type.
3. Optionally add a Jinja2 output template for a custom display.
4. Save. The template is now available in the **Parser template** dropdown on job forms.

## Tips

- Always test with real device output before attaching a template to a scheduled job. The test bed returns results in seconds.
- TextFSM `Value` names become the column headers in the run detail table — choose names that are self-explanatory (`VERSION`, `HOSTNAME`, `INTERFACE`, `STATUS`).
- If the parser returns 0 rows for valid input, check that the `Record` action (TextFSM) or the group anchoring (TTP) matches the actual line structure. Newline differences (CRLF vs LF) can cause silent mismatches.
- For `cve_scan` jobs, the parser **must** produce a field named `version` (case-sensitive). All other fields are ignored by the CVE scanner.
- XSLT is advanced — use it only when you have NETCONF XML and need to extract specific subtrees that can't be handled with simpler tools.
