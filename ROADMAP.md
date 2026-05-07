# Kiroku Roadmap

## CVE Detection

Detect known vulnerabilities on network devices by collecting firmware version
information via CLI commands and cross-referencing against a CVE database.

### How it fits the existing infrastructure

The `collect` job kind already handles the first half of this feature:

- A Profile defines commands (`show version`) and a parser template (TextFSM/TTP)
  that extracts structured fields from the output.
- The worker executes the commands, parses the output, and returns structured rows
  in `JobResult.parsed`.
- The recorder stores the run result.

The missing pieces are: what to do with the parsed version string after collection,
and where to store CVE results.

---

### Phase 1 — Version extraction

Add two optional fields to the `Profile` model:

| Field | Purpose |
|---|---|
| `cve_vendor` | CPE vendor string (e.g. `cisco`) |
| `cve_product` | CPE product string (e.g. `ios`, `ios_xe`, `junos`) |

A profile with these fields set, combined with a parser template that extracts
`{"version": "17.3.4"}`, becomes a CVE-scan-capable profile. The parser template
handles version normalization — TextFSM is well-suited here since NTC templates
already exist for `show version` on most major platforms.

**Migration:** add `cve_vendor` (`String(64)`, nullable) and `cve_product`
(`String(64)`, nullable) to the `profiles` table.

---

### Phase 2 — New job kind: `cve_scan`

Add `cve_scan` to the `JobKind` enum. The worker handles it identically to
`collect` (runs commands, parses output) and then:

1. Pulls `version` from the parsed dict.
2. Constructs a CPE string: `cpe:2.3:o:{vendor}:{product}:{version}:*:*:*:*:*:*:*`
3. Calls the CVE API with that CPE.
4. Includes CVE results in the `JobResult`.

`cve_scan` appears in the Schedule kind dropdown alongside `backup` and `collect`.

---

### Phase 3 — CVE API

Two provider options:

| | NVD (NIST) | OpenCVE |
|---|---|---|
| Auth | API key (free, optional) | Account required |
| Rate limit | 5 req/s with key, 1/s without | 60/min free tier |
| CPE search | `GET /cves/2.0?cpeName=...` | `GET /api/cves?cpe=...` |
| Data quality | Authoritative source | Aggregates NVD + enriches |
| Best for | Getting started, no signup | Richer metadata, subscriptions |

**Recommendation:** Start with NVD — it is the authoritative source, requires no
account, and OpenCVE is a layer on top of it anyway. OpenCVE can be added as a
second provider later using the same pluggable pattern as credential providers.

The `CveClient` abstraction mirrors the `CredentialResolver` pattern:

```python
class CveClient(ABC):
    @abstractmethod
    def query_cpe(self, cpe: str) -> list[CveEntry]: ...
```

Concrete implementations: `NvdCveClient`, `OpenCveCveClient`.

---

### Phase 4 — New models

```
cve_scans
  id            serial primary key
  run_id        int references runs(id) on delete set null
  device_id     int references devices(id) on delete cascade
  cpe           varchar(256)
  version_found varchar(128)
  raw_version   varchar(128)
  scanned_at    timestamptz

cve_results
  id            serial primary key
  scan_id       int references cve_scans(id) on delete cascade
  cve_id        varchar(32)        -- e.g. CVE-2023-20198
  cvss_v3_score numeric(4,1)
  severity      varchar(16)        -- CRITICAL / HIGH / MEDIUM / LOW
  summary       text
  published_at  timestamptz
  url           varchar(512)
```

The recorder gains a `_record_cve_scan()` path that writes these rows when
`job_kind == "cve_scan"`.

---

### Phase 5 — UI additions

- **Profile form:** `cve_vendor` and `cve_product` fields (shown for CLI profiles).
- **Schedule form:** `cve_scan` available in the Kind dropdown.
- **New page `/cve`:** table of recent scans — device, version found, CVE count,
  highest severity, scan timestamp.
- **Device list:** CVE badge per device showing count and highest severity from the
  most recent scan (colour-coded: critical/high/medium/low/none).

---

### Version normalization and confidence scoring

Vendor firmware version strings do not match CPE format verbatim:

| Platform | Raw version | CPE version |
|---|---|---|
| Cisco IOS | `17.03.04a` | `17.3.4a` |
| Cisco IOS XE | `17.3.4a` | `17.3.4a` |
| Juniper JunOS | `21.4R1.12` | `21.4r1.12` |
| Arista EOS | `4.28.3F` | `4.28.3f` |

**Approach:** Use fuzzy matching against CPE entries returned by the CVE API,
scoring each candidate match and surfacing the confidence score to the operator
in the UI. This avoids requiring exact version string normalization up front while
still giving operators visibility into how certain the match is. The parser
template controls what version string is extracted; the fuzzy matcher handles
the CPE alignment and reports how confident it is in the result.

---

### Implementation order

1. DB migration: `cve_vendor` + `cve_product` on `profiles`; `cve_scans` and
   `cve_results` tables.
2. Add `cve_scan` to `JobKind`; wire through `JobSpec` and the scheduler.
3. `CveClient` abstraction with NVD backend (pluggable, same pattern as credential
   providers).
4. Worker `_run_cve_scan()` function.
5. Recorder `_record_cve_scan()`.
6. Profile form fields; Schedule kind dropdown update.
7. CVE scans UI page and device list badges.
