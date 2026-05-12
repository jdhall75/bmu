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

## Saving and using a template

1. Click **New parser template** or open an existing one via **Edit**.
2. Paste the template body and choose the type.
3. Save. The template is now available in the **Parser template** dropdown on job forms.

## Tips

- Always test with real device output before attaching a template to a scheduled job. The test bed returns results in seconds.
- TextFSM `Value` names become the column headers in the run detail table — choose names that are self-explanatory (`VERSION`, `HOSTNAME`, `INTERFACE`, `STATUS`).
- If the parser returns 0 rows for valid input, check that the `Record` action (TextFSM) or the group anchoring (TTP) matches the actual line structure. Newline differences (CRLF vs LF) can cause silent mismatches.
- For `cve_scan` jobs, the parser **must** produce a field named `version` (case-sensitive). All other fields are ignored by the CVE scanner.
- XSLT is advanced — use it only when you have NETCONF XML and need to extract specific subtrees that can't be handled with simpler tools.
