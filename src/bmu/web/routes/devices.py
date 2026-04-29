from litestar import Router, get, post
from litestar.params import Body
from litestar.enums import RequestEncodingType
from litestar.response import Redirect, Template
from sqlalchemy import select
from sqlalchemy.orm import Session

from bmu.models import Credential, Device, DeviceGroup, Profile
from bmu.web.deps import provide_db


@get("/", dependencies={"db": provide_db})
async def list_devices(db: Session) -> Template:
    devices = db.scalars(select(Device).order_by(Device.name)).all()
    return Template(template_name="devices/list.html", context={"devices": devices})


@get("/new", dependencies={"db": provide_db})
async def new_device(db: Session) -> Template:
    return Template(
        template_name="devices/form.html",
        context={
            "device": None,
            "groups": db.scalars(select(DeviceGroup).order_by(DeviceGroup.name)).all(),
            "profiles": db.scalars(select(Profile).order_by(Profile.name)).all(),
            "credentials": db.scalars(select(Credential).order_by(Credential.name)).all(),
        },
    )


@post("/", dependencies={"db": provide_db})
async def create_device(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    d = Device(
        name=data["name"],
        hostname=data["hostname"],
        port=int(data["port"]) if data.get("port") else None,
        description=data.get("description") or None,
        group_id=int(data["group_id"]),
        profile_id=int(data["profile_id"]),
        credential_id=int(data["credential_id"]) if data.get("credential_id") else None,
        enabled=bool(data.get("enabled")),
    )
    db.add(d)
    db.commit()
    return Redirect(path="/devices")


router = Router(path="/devices", route_handlers=[list_devices, new_device, create_device])
