from litestar import Router, get, post
from litestar.datastructures import UploadFile
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Redirect, Response, Template
from sqlalchemy import select
from sqlalchemy.orm import Session

from bmu.models import Credential, Device, DeviceGroup, Profile
from bmu.web.deps import provide_db
from bmu.web.import_devices import import_csv

CSV_TEMPLATE = (
    "name,hostname,port,description,group,profile,credentials,enabled\n"
    "edge-rtr-01,10.0.0.1,22,Core edge router,core,cisco-iosxe-backup,core-admin,1\n"
)


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


@get("/import")
async def import_form() -> Template:
    return Template(template_name="devices/import.html", context={})


@get("/import/template")
async def import_template() -> Response:
    return Response(
        content=CSV_TEMPLATE,
        media_type="text/csv",
        headers={"content-disposition": 'attachment; filename="bmu-devices-template.csv"'},
    )


@post("/import", dependencies={"db": provide_db})
async def import_submit(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.MULTI_PART),
) -> Template:
    upload = data.get("file")
    pasted = (data.get("pasted") or "").strip() if isinstance(data.get("pasted"), str) else ""

    raw = ""
    if isinstance(upload, UploadFile):
        content = await upload.read()
        if content:
            raw = content.decode("utf-8-sig", errors="replace")
    if not raw and pasted:
        raw = pasted

    if not raw:
        return Template(
            template_name="devices/import_results.html",
            context={"results": [], "created": 0,
                     "error": "Provide a CSV file or paste CSV text."},
        )

    try:
        results, created = import_csv(db, raw)
    except Exception as exc:
        db.rollback()
        return Template(
            template_name="devices/import_results.html",
            context={"results": [], "created": 0, "error": f"{type(exc).__name__}: {exc}"},
        )

    return Template(
        template_name="devices/import_results.html",
        context={"results": results, "created": created, "error": None},
    )


router = Router(
    path="/devices",
    route_handlers=[
        list_devices,
        new_device,
        create_device,
        import_form,
        import_template,
        import_submit,
    ],
)
