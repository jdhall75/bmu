"""CVE query facade.

``query_cpe(cpe)`` is the single entry point called by the worker.
Provider selection is controlled by settings.cve_provider (default: "nvd").
"""
from __future__ import annotations

from kiroku.cve.base import CveEntry


def query_cpe(cpe: str) -> list[dict]:
    """Return CVE entries for the given CPE string as plain dicts."""
    from kiroku.config import get_settings
    from kiroku.cve.nvd import NvdCveClient

    settings = get_settings()
    client = NvdCveClient(api_key=getattr(settings, "nvd_api_key", None))
    entries: list[CveEntry] = client.query_cpe(cpe)
    return [e.as_dict() for e in entries]
