from litestar import Router, get
from litestar.response import Template
from sqlalchemy import select
from sqlalchemy.orm import Session

from kiroku.models import CveScan
from kiroku.web.deps import provide_db

_SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


def _highest_severity(results) -> str | None:
    best = None
    best_rank = -1
    for r in results:
        rank = _SEVERITY_ORDER.get(r.severity or "", 0)
        if rank > best_rank:
            best_rank = rank
            best = r.severity
    return best


@get("/", dependencies={"db": provide_db})
async def list_cve_scans(db: Session) -> Template:
    scans = db.scalars(
        select(CveScan).order_by(CveScan.scanned_at.desc()).limit(500)
    ).all()

    rows = []
    for scan in scans:
        rows.append(
            {
                "scan": scan,
                "device_name": scan.device.name if scan.device else f"device:{scan.device_id}",
                "cve_count": len(scan.results),
                "highest_severity": _highest_severity(scan.results),
            }
        )

    return Template(template_name="cve/list.html", context={"rows": rows})


router = Router(path="/cve", route_handlers=[list_cve_scans])
