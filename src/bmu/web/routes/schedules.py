from litestar import Router, get, post
from litestar.params import Body
from litestar.enums import RequestEncodingType
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER
from sqlalchemy import select
from sqlalchemy.orm import Session

from bmu.models import DeviceGroup, JobKind, Schedule
from bmu.web.deps import provide_db


def _schedule_form_context(db: Session, schedule=None) -> dict:
    return {
        "schedule": schedule,
        "groups": db.scalars(select(DeviceGroup).order_by(DeviceGroup.name)).all(),
        "kinds": [k.value for k in JobKind],
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


@post("/", dependencies={"db": provide_db})
async def create_schedule(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    s = Schedule(
        name=data["name"],
        description=data.get("description") or None,
        group_id=int(data["group_id"]),
        kind=JobKind(data["kind"]),
        cron=data["cron"],
        timezone=data.get("timezone") or "UTC",
        enabled=bool(data.get("enabled")),
    )
    db.add(s)
    db.commit()
    return Redirect(path="/schedules")


@get("/{schedule_id:int}/edit", dependencies={"db": provide_db})
async def edit_schedule(schedule_id: int, db: Session) -> Template:
    schedule = db.get(Schedule, schedule_id)
    return Template(
        template_name="schedules/form.html",
        context=_schedule_form_context(db, schedule),
    )


@post("/{schedule_id:int}", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER)
async def update_schedule(
    schedule_id: int,
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    schedule = db.get(Schedule, schedule_id)
    schedule.name = data["name"]
    schedule.description = data.get("description") or None
    schedule.group_id = int(data["group_id"])
    schedule.kind = JobKind(data["kind"])
    schedule.cron = data["cron"]
    schedule.timezone = data.get("timezone") or "UTC"
    schedule.enabled = bool(data.get("enabled"))
    db.commit()
    return Redirect(path="/schedules")


@post("/{schedule_id:int}/delete", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER)
async def delete_schedule(schedule_id: int, db: Session) -> Redirect:
    schedule = db.get(Schedule, schedule_id)
    if schedule:
        db.delete(schedule)
        db.commit()
    return Redirect(path="/schedules")


router = Router(
    path="/schedules",
    route_handlers=[
        list_schedules,
        new_schedule,
        create_schedule,
        edit_schedule,
        update_schedule,
        delete_schedule,
    ],
)
