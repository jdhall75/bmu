from litestar import Router, get, post
from litestar.params import Body
from litestar.enums import RequestEncodingType
from litestar.response import Redirect, Template
from sqlalchemy import select
from sqlalchemy.orm import Session

from bmu.models import DeviceGroup, JobKind, Schedule
from bmu.web.deps import provide_db


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
        context={
            "groups": db.scalars(select(DeviceGroup).order_by(DeviceGroup.name)).all(),
            "kinds": [k.value for k in JobKind],
        },
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


router = Router(
    path="/schedules", route_handlers=[list_schedules, new_schedule, create_schedule]
)
