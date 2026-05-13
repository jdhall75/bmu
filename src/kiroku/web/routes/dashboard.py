from litestar import Router, get
from litestar.response import Template
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kiroku.models import Device, DeviceGroup, Job, RunBatch, Schedule
from kiroku.web.deps import provide_db


@get("/", dependencies={"db": provide_db})
async def index(db: Session) -> Template:
    counts = {
        "groups": db.scalar(select(func.count()).select_from(DeviceGroup)) or 0,
        "devices": db.scalar(select(func.count()).select_from(Device)) or 0,
        "schedules": db.scalar(select(func.count()).select_from(Schedule)) or 0,
        "jobs_executed": db.scalar(select(func.count()).select_from(RunBatch)) or 0,
    }
    rows = db.execute(
        select(RunBatch, Job.name.label("job_name"))
        .outerjoin(Schedule, RunBatch.schedule_id == Schedule.id)
        .outerjoin(Job, Schedule.job_id == Job.id)
        .order_by(RunBatch.created_at.desc())
        .limit(20)
    ).all()
    recent_batches = [
        {"batch": b, "job_name": job_name or b.schedule_name} for b, job_name in rows
    ]
    failing = (
        db.scalar(select(func.count()).select_from(RunBatch).where(RunBatch.failed > 0))
        or 0
    )
    return Template(
        template_name="dashboard.html",
        context={
            "counts": counts,
            "recent_batches": recent_batches,
            "failing": failing,
        },
    )


router = Router(path="/", route_handlers=[index])
