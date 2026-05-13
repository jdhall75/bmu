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

### Variables available inside the template

| Variable | Type | Description |
|----------|------|-------------|
| `rows` | `list[dict]` | Every parsed row. Always a list, even for single-row output. |
| `headers` | `list[str]` | The keys from the first row (column names). |
| `data` | same as `rows` | Alias for `rows`. Use whichever reads more naturally. |

Each dict in `rows` has the same keys as the `Value` names in a TextFSM template (or group keys for TTP).

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

**Summary card** — highlight totals or key fields:

```jinja2
{% set r = rows[0] %}
<dl class="detail-grid">
  <dt>Hostname</dt><dd>{{ r.HOSTNAME }}</dd>
  <dt>Version</dt><dd>{{ r.VERSION }}</dd>
  <dt>Uptime</dt><dd>{{ r.UPTIME }}</dd>
</dl>
```

**Conditional formatting** — colour-code a status field:

```jinja2
<ul>
{% for r in rows %}
  <li>
    <strong>{{ r.INTERFACE }}</strong>
    {% if r.STATUS == 'up' %}
      <span class="status status-success">up</span>
    {% else %}
      <span class="status status-failed">{{ r.STATUS }}</span>
    {% endif %}
    — {{ r.PROTOCOL }}
  </li>
{% endfor %}
</ul>
```

**Filter rows inside the template** — show only down interfaces:

```jinja2
{% set down = rows | selectattr('STATUS', 'ne', 'up') | list %}
{% if down %}
<p><strong>{{ down | length }} interface(s) down:</strong></p>
<ul>
  {% for r in down %}<li>{{ r.INTERFACE }}</li>{% endfor %}
</ul>
{% else %}
<p class="muted">All interfaces are up.</p>
{% endif %}
```

### Notes

- The template runs in a **sandboxed Jinja2 environment** — standard filters (`| upper`, `| length`, `| join`, `selectattr`, `map`, etc.) all work, but arbitrary Python execution is blocked.
- If the template raises an error, a red **Template error** block is shown on the run detail page with the exception message. Fix the template and re-run the job to get a clean render.
- Leave the field blank to keep the default auto-generated table.
- You can use Kiroku's existing CSS classes (`detail-grid`, `table-wrap`, `status`, `status-success`, `status-failed`, `muted`) to make the output match the rest of the UI.

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
