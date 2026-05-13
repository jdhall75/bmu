"""NVD (NIST) CVE API client.

Queries https://services.nvd.nist.gov/rest/json/cves/2.0 by CPE name.
An optional API key raises the rate limit from 1 req/s to 5 req/s.
"""

from __future__ import annotations

import urllib.parse
import urllib.request

from kiroku.cve.base import CveClient, CveEntry
from kiroku.logging import get_logger

log = get_logger(__name__)

_NVD_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"


def _extract_severity(cve_node: dict) -> tuple[float | None, str | None]:
    metrics = cve_node.get("metrics", {})
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(key, [])
        if entries:
            cvss = entries[0].get("cvssData", {})
            score = cvss.get("baseScore")
            severity = cvss.get("baseSeverity")
            return (float(score) if score is not None else None, severity)
    return None, None


class NvdCveClient(CveClient):
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    def query_cpe(self, cpe: str) -> list[CveEntry]:
        url = f"{_NVD_BASE}?cpeName={urllib.parse.quote(cpe, safe='')}"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "kiroku/1.0")
        if self._api_key:
            req.add_header("apiKey", self._api_key)

        import json

        log.debug("querying NVD", cpe=cpe)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read())
        except Exception as exc:
            log.error("NVD request failed", cpe=cpe, error=str(exc))
            return []

        entries: list[CveEntry] = []
        for vuln in body.get("vulnerabilities", []):
            cve = vuln.get("cve", {})
            cve_id = cve.get("id", "")
            score, severity = _extract_severity(cve)

            descriptions = cve.get("descriptions", [])
            summary = next(
                (d["value"] for d in descriptions if d.get("lang") == "en"), None
            )

            refs = cve.get("references", [])
            url_val = (
                refs[0]["url"] if refs else f"https://nvd.nist.gov/vuln/detail/{cve_id}"
            )

            entries.append(
                CveEntry(
                    cve_id=cve_id,
                    cvss_v3_score=score,
                    severity=severity,
                    summary=summary,
                    published_at=cve.get("published"),
                    url=url_val,
                )
            )

        log.info("NVD query complete", cpe=cpe, count=len(entries))
        return entries
