from litestar import Router, get
from litestar.response import Template
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bmu.models import Device, DeviceGroup, Run, RunStatus, Schedule
from bmu.web.deps import provide_db


@get("/", dependencies={"db": provide_db})
async def index(db: Session) -> Template:
    counts = {
        "groups": db.scalar(select(func.count()).select_from(DeviceGroup)) or 0,
        "devices": db.scalar(select(func.count()).select_from(Device)) or 0,
        "schedules": db.scalar(select(func.count()).select_from(Schedule)) or 0,
        "runs": db.scalar(select(func.count()).select_from(Run)) or 0,
    }
    recent_runs = db.scalars(
        select(Run).order_by(Run.created_at.desc()).limit(20)
    ).all()
    failing = db.scalar(
        select(func.count()).select_from(Run).where(Run.status == RunStatus.FAILED)
    ) or 0
    return Template(
        template_name="dashboard.html",
        context={"counts": counts, "recent_runs": recent_runs, "failing": failing},
    )


router = Router(path="/", route_handlers=[index])
