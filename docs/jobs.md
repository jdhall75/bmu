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

## NETCONF jobs

When a device has **Driver kind = netconf**, the job's **RPC** field is sent verbatim via the NETCONF session instead of executing CLI commands. The raw XML response is used as the job output — stored as the backup text for `backup` jobs, or passed to the parser for `collect` jobs.

### Device prerequisites

1. Set **Driver kind** to `netconf` on the device.
2. Leave **Port** blank (defaults to 830) or set it explicitly if the router uses a non-standard port.
3. The **Platform** field is not used for NETCONF jobs.

### RPC format

Every RPC must be a complete XML fragment starting with `<rpc>`, including a `message-id` attribute:

```xml
<rpc message-id="101" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <!-- operation goes here -->
</rpc>
```

The `message-id` value is arbitrary — `101` is conventional.

### Generic examples

**Standard get-config (any NETCONF device)**

```xml
<rpc message-id="101" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <get-config>
    <source><running/></source>
  </get-config>
</rpc>
```

**Standard get with a subtree filter**

```xml
<rpc message-id="101" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <get>
    <filter type="subtree">
      <interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces"/>
    </filter>
  </get>
</rpc>
```

### Juniper JunOS examples

Juniper exposes its own operational RPCs in addition to the standard `get-config`.

**Backup — full configuration as plain text**

Use this as a `backup` job to store a human-readable config in Git:

```xml
<rpc message-id="101" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <get-configuration format="text"/>
</rpc>
```

**Backup — full configuration as XML**

Use this when you want to preserve the structured XML in Git or run an XSLT parser over it:

```xml
<rpc message-id="101" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <get-configuration format="xml"/>
</rpc>
```

**Collect — interface information**

Use this as a `collect` job (optionally with an XSLT parser template to extract specific fields):

```xml
<rpc message-id="101" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <get-interface-information/>
</rpc>
```

**Collect — chassis / hardware inventory**

```xml
<rpc message-id="101" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <get-chassis-inventory/>
</rpc>
```

**Collect — routing table summary**

```xml
<rpc message-id="101" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <get-route-summary-information/>
</rpc>
```

**Collect — software version**

```xml
<rpc message-id="101" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <get-software-information/>
</rpc>
```

### Parsing NETCONF output

NETCONF responses are XML, so the **xslt** parser type is the most natural fit. Attach an XSLT template to a `collect` job to extract rows from the response. For example, to pull interface names and oper-status from a `get-interface-information` response:

```xslt
<?xml version="1.0"?>
<xsl:stylesheet version="1.0"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="text"/>
  <xsl:template match="/">
    <xsl:for-each select="//physical-interface">
name=<xsl:value-of select="name"/>
oper=<xsl:value-of select="oper-status"/>
admin=<xsl:value-of select="admin-status"/>
    </xsl:for-each>
  </xsl:template>
</xsl:stylesheet>
```

See [Parsers](parsers) for full parser documentation and the test bed.

## Tips

- For `backup` jobs, put `show running-config` (or `display current-configuration` for Huawei, `show configuration` for JunOS) as the single command. The entire output is committed to Git verbatim.
- For `collect` jobs, you can run multiple commands — all output is joined and passed to the parser as one string. Make sure your parser template handles the combined output correctly.
- A `collect` job without a parser template still runs successfully — the raw command output is captured and the run is marked successful, but no structured rows are stored and no ✓ badge appears in the batch table.
- If you want to test a parser before attaching it to a job, go to **Parsers → Test bed** and paste real device output there.
- `cve_scan` jobs require the parser to produce a row containing a `version` field. If the parser returns no `version` key, the CVE lookup is skipped.
