from litestar import Router, get, post
from litestar.params import Body
from litestar.enums import RequestEncodingType
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER
from sqlalchemy import select
from sqlalchemy.orm import Session

from kiroku.models import Credential, DeviceGroup
from kiroku.web.deps import provide_db


def _parse_ids(data: dict) -> list[int]:
    raw = data.get("ids", [])
    if isinstance(raw, str):
        raw = [raw]
    return [int(i) for i in raw if i]


def _group_form_context(db: Session, group=None) -> dict:
    return {
        "group": group,
        "credentials": db.scalars(select(Credential).order_by(Credential.name)).all(),
    }


@get("/", dependencies={"db": provide_db})
async def list_groups(db: Session) -> Template:
    groups = db.scalars(select(DeviceGroup).order_by(DeviceGroup.name)).all()
    return Template(template_name="groups/list.html", context={"groups": groups})


@get("/new", dependencies={"db": provide_db})
async def new_group(db: Session) -> Template:
    return Template(
        template_name="groups/form.html",
        context=_group_form_context(db),
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


@post("/bulk", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER)
async def bulk_groups(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    ids = _parse_ids(data)
    if ids and data.get("action") == "delete":
        for group in db.scalars(select(DeviceGroup).where(DeviceGroup.id.in_(ids))).all():
            db.delete(group)
        db.commit()
    return Redirect(path="/groups")


@get("/{group_id:int}/edit", dependencies={"db": provide_db})
async def edit_group(group_id: int, db: Session) -> Template:
    group = db.get(DeviceGroup, group_id)
    return Template(
        template_name="groups/form.html",
        context=_group_form_context(db, group),
    )


@post("/{group_id:int}", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER)
async def update_group(
    group_id: int,
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    group = db.get(DeviceGroup, group_id)
    group.name = data["name"]
    group.description = data.get("description") or None
    group.max_parallel = int(data.get("max_parallel") or 8)
    group.default_credential_id = (
        int(data["default_credential_id"]) if data.get("default_credential_id") else None
    )
    db.commit()
    return Redirect(path="/groups")


@post("/{group_id:int}/delete", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER)
async def delete_group(group_id: int, db: Session) -> Redirect:
    group = db.get(DeviceGroup, group_id)
    if group:
        db.delete(group)
        db.commit()
    return Redirect(path="/groups")


@get("/{group_id:int}", dependencies={"db": provide_db})
async def view_group(db: Session, group_id: int) -> Template:
    group = db.get(DeviceGroup, group_id)
    return Template(template_name="groups/detail.html", context={"group": group})


router = Router(
    path="/groups",
    route_handlers=[
        list_groups,
        new_group,
        create_group,
        bulk_groups,
        edit_group,
        update_group,
        delete_group,
        view_group,
    ],
)
