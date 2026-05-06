from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class CveEntry:
    cve_id: str
    cvss_v3_score: float | None
    severity: str | None  # CRITICAL / HIGH / MEDIUM / LOW / NONE
    summary: str | None
    published_at: str | None  # ISO timestamp
    url: str

    def as_dict(self) -> dict:
        return {
            "cve_id": self.cve_id,
            "cvss_v3_score": self.cvss_v3_score,
            "severity": self.severity,
            "summary": self.summary,
            "published_at": self.published_at,
            "url": self.url,
        }


class CveClient(ABC):
    @abstractmethod
    def query_cpe(self, cpe: str) -> list[CveEntry]: ...
