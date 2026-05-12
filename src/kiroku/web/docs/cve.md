# CVE Scans

The CVE Scans page shows the results of `cve_scan` job runs. For each device, it shows the OS version that was detected, the CPE string used for the lookup, the number of CVEs found, and the highest severity.

## How it works

1. A `cve_scan` job runs the configured commands against the device.
2. The parser template extracts a field named `version` from the command output.
3. Kiroku constructs a CPE 2.3 string: `cpe:2.3:o:<vendor>:<product>:<version>:*:*:*:*:*:*:*`
4. The NVD (National Vulnerability Database) API is queried for CVEs matching that CPE.
5. Results are stored in the database and shown on this page.

## Setup requirements

To get CVE scan results you need:

1. A credential assigned to the device or group.
2. A `cve_scan` job with:
   - Commands that produce version output (e.g. `show version`)
   - A parser template that extracts a `version` field
   - A **CVE vendor** (e.g. `cisco`)
   - A **CVE product** (e.g. `ios_xe`, `nxos`, `ios_xr`)
3. A schedule (or use **Run now** for an immediate scan).

## CPE vendor and product values

The vendor and product strings must match NVD's CPE dictionary exactly. Some common examples:

| Platform | Vendor | Product |
|----------|--------|---------|
| Cisco IOS-XE | `cisco` | `ios_xe` |
| Cisco IOS-XR | `cisco` | `ios_xr` |
| Cisco NX-OS | `cisco` | `nx-os` |
| Arista EOS | `arista` | `eos` |
| Juniper JunOS | `juniper` | `junos` |

If you're unsure of the exact values, search the [NVD CPE dictionary](https://nvd.nist.gov/products/cpe/search) for your product.

## Severity levels

Kiroku uses the CVSS v3 severity scale:

| Level | Score range | Colour |
|-------|------------|--------|
| **CRITICAL** | 9.0 – 10.0 | Red |
| **HIGH** | 7.0 – 8.9 | Orange |
| **MEDIUM** | 4.0 – 6.9 | Yellow |
| **LOW** | 0.1 – 3.9 | Green |
| **NONE** | 0.0 | Grey (no CVEs found) |

The badge on the devices list shows the *highest* severity CVE found for that device at the last scan.

## Version detection

The parser must produce at least one row containing a `version` key. For example, a TextFSM template for `show version` on Cisco IOS-XE might define:

```
Value VERSION ([\d.()A-Za-z]+)
```

If no `version` field is found in the parsed output, the CVE lookup is skipped and the scan record shows no version and no CVEs.

## Tips

- Scan frequency: CVEs for mature software versions don't appear overnight. Weekly or monthly scans are typically sufficient.
- If a device shows 0 CVEs but you expect some, verify the `version` field is being extracted correctly using the **Parser test bed** with real `show version` output.
- Different images of the same platform can have completely different CVE exposure. It's worth scanning after every software upgrade even if the regular schedule hasn't run yet — use **Run now** on the job.
- CVE data comes from the NVD API (api.nvd.nist.gov). If the API is unavailable, the scan run still succeeds (the device commands are executed) but no CVE entries are stored. The version is still recorded.
