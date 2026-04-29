from litestar import Router, get, post
from litestar.params import Body
from litestar.enums import RequestEncodingType
from litestar.response import Redirect, Template
from sqlalchemy import select
from sqlalchemy.orm import Session

from bmu.models import Credential, DeviceGroup
from bmu.web.deps import provide_db


@get("/", dependencies={"db": provide_db})
async def list_groups(db: Session) -> Template:
    groups = db.scalars(select(DeviceGroup).order_by(DeviceGroup.name)).all()
    return Template(template_name="groups/list.html", context={"groups": groups})


@get("/new", dependencies={"db": provide_db})
async def new_group(db: Session) -> Template:
    creds = db.scalars(select(Credential).order_by(Credential.name)).all()
    return Template(
        template_name="groups/form.html",
        context={"group": None, "credentials": creds},
    )


@post("/", dependencies={"db": provide_db})
async def create_group(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    g = DeviceGroup(
        name=data["name"],
        description=data.get("description") or None,
        max_parallel=int(data.get("max_parallel") or 8),
        default_credential_id=int(data["default_credential_id"])
        if data.get("default_credential_id")
        else None,
    )
    db.add(g)
    db.commit()
    return Redirect(path="/groups")


@get("/{group_id:int}", dependencies={"db": provide_db})
async def view_group(db: Session, group_id: int) -> Template:
    group = db.get(DeviceGroup, group_id)
    return Template(template_name="groups/detail.html", context={"group": group})


router = Router(
    path="/groups",
    route_handlers=[list_groups, new_group, create_group, view_group],
)
