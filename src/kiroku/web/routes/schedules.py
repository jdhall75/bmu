from litestar import Router, get, post
from litestar.params import Body
from litestar.enums import RequestEncodingType
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER
from sqlalchemy import select
from sqlalchemy.orm import Session

from kiroku.models import Job, Schedule
from kiroku.web.auth import require_admin, require_authenticated
from kiroku.web.deps import provide_db
from kiroku.web.helpers import parse_ids


def _schedule_form_context(db: Session, schedule=None) -> dict:
    return {
        "schedule": schedule,
        "jobs": db.scalars(select(Job).order_by(Job.name)).all(),
    }


@get("/", dependencies={"db": provide_db})
async def list_schedules(db: Session) -> Template:
    schedules = db.scalars(select(Schedule).order_by(Schedule.name)).all()
    return Template(
        template_name="schedules/list.html", context={"schedules": schedules}
    )


@get("/new", dependencies={"db": provide_db})
async def new_schedule(db: Session) -> Template:
    return Template(
        template_name="schedules/form.html",
        context=_schedule_form_context(db),
    )


@post("/", dependencies={"db": provide_db}, guards=[require_admin])
async def create_schedule(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    s = Schedule(
        name=data["name"],
        description=data.get("description") or None,
        job_id=int(data["job_id"]) if data.get("job_id") else None,
        cron=data["cron"],
        timezone=data.get("timezone") or "UTC",
        enabled=bool(data.get("enabled")),
    )
    db.add(s)
    db.commit()
    return Redirect(path="/schedules")


@post("/bulk", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER, guards=[require_admin])
async def bulk_schedules(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    ids = parse_ids(data)
    if ids and data.get("action") == "delete":
        for schedule in db.scalars(select(Schedule).where(Schedule.id.in_(ids))).all():
            db.delete(schedule)
        db.commit()
    return Redirect(path="/schedules")


@get("/{schedule_id:int}/edit", dependencies={"db": provide_db})
async def edit_schedule(schedule_id: int, db: Session) -> Template:
    schedule = db.get(Schedule, schedule_id)
    return Template(
        template_name="schedules/form.html",
        context=_schedule_form_context(db, schedule),
    )


@post(
    "/{schedule_id:int}",
    dependencies={"db": provide_db},
    status_code=HTTP_303_SEE_OTHER,
    guards=[require_admin],
)
async def update_schedule(
    schedule_id: int,
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    schedule = db.get(Schedule, schedule_id)
    schedule.name = data["name"]
    schedule.description = data.get("description") or None
    schedule.job_id = int(data["job_id"]) if data.get("job_id") else None
    schedule.cron = data["cron"]
    schedule.timezone = data.get("timezone") or "UTC"
    schedule.enabled = bool(data.get("enabled"))
    db.commit()
    return Redirect(path="/schedules")


@post(
    "/{schedule_id:int}/delete",
    dependencies={"db": provide_db},
    status_code=HTTP_303_SEE_OTHER,
    guards=[require_admin],
)
async def delete_schedule(schedule_id: int, db: Session) -> Redirect:
    schedule = db.get(Schedule, schedule_id)
    if schedule:
        db.delete(schedule)
        db.commit()
    return Redirect(path="/schedules")


@post(
    "/{schedule_id:int}/skip-next",
    dependencies={"db": provide_db},
    status_code=HTTP_303_SEE_OTHER,
    guards=[require_admin],
)
async def skip_next_run(schedule_id: int, db: Session) -> Redirect:
    schedule = db.get(Schedule, schedule_id)
    if schedule:
        schedule.skip_next_run = not schedule.skip_next_run
        db.commit()
    return Redirect(path="/schedules")


router = Router(
    path="/schedules",
    guards=[require_authenticated],
    route_handlers=[
        list_schedules,
        new_schedule,
        create_schedule,
        bulk_schedules,
        edit_schedule,
        update_schedule,
        delete_schedule,
        skip_next_run,
    ],
)
