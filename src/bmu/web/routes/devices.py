from litestar import Router, get, post
from litestar.datastructures import UploadFile
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Redirect, Response, Template
from litestar.status_codes import HTTP_303_SEE_OTHER
from sqlalchemy import select
from sqlalchemy.orm import Session

from bmu.models import Credential, CveScan, Device, DeviceGroup, Profile
from bmu.web.deps import provide_db
from bmu.web.import_devices import import_csv

_SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


def _cve_badges(db: Session) -> dict[int, dict]:
    """Return {device_id: {count, severity}} from the latest scan per device."""
    badges: dict[int, dict] = {}
    for scan in db.scalars(select(CveScan).order_by(CveScan.scanned_at.desc())).all():
        if scan.device_id in badges:
            continue
        best_sev = None
        best_rank = -1
        for r in scan.results:
            rank = _SEVERITY_ORDER.get(r.severity or "", 0)
            if rank > best_rank:
                best_rank = rank
                best_sev = r.severity
        badges[scan.device_id] = {"count": len(scan.results), "severity": best_sev}
    return badges

CSV_TEMPLATE = (
    "name,hostname,port,description,group,profile,credentials,enabled\n"
    "edge-rtr-01,10.0.0.1,22,Core edge router,core,cisco-iosxe-backup,core-admin,1\n"
)


def _device_form_options(db: Session) -> dict:
    return {
        "groups": db.scalars(select(DeviceGroup).order_by(DeviceGroup.name)).all(),
        "profiles": db.scalars(select(Profile).order_by(Profile.name)).all(),
        "credentials": db.scalars(select(Credential).order_by(Credential.name)).all(),
    }


def _device_form_context(db: Session, device=None) -> dict:
    return {"device": device, **_device_form_options(db)}


def _parse_ids(data: dict) -> list[int]:
    raw = data.get("ids", [])
    if isinstance(raw, str):
        raw = [raw]
    return [int(i) for i in raw if i]


@get("/", dependencies={"db": provide_db})
async def list_devices(db: Session) -> Template:
    devices = db.scalars(select(Device).order_by(Device.name)).all()
    return Template(
        template_name="devices/list.html",
        context={"devices": devices, "cve_badges": _cve_badges(db), **_device_form_options(db)},
    )


@get("/new", dependencies={"db": provide_db})
async def new_device(db: Session) -> Template:
    return Template(
        template_name="devices/form.html",
        context=_device_form_context(db),
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


@post("/bulk", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER)
async def bulk_devices(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    ids = _parse_ids(data)
    action = data.get("action")

    if not ids:
        return Redirect(path="/devices")

    if action == "delete":
        for device in db.scalars(select(Device).where(Device.id.in_(ids))).all():
            db.delete(device)
        db.commit()

    elif action == "edit":
        for device in db.scalars(select(Device).where(Device.id.in_(ids))).all():
            if data.get("bulk_port"):
                device.port = int(data["bulk_port"])
            if data.get("bulk_group_id"):
                device.group_id = int(data["bulk_group_id"])
            if data.get("bulk_profile_id"):
                device.profile_id = int(data["bulk_profile_id"])
            bulk_cred = data.get("bulk_credential_id", "")
            if bulk_cred == "NONE":
                device.credential_id = None
            elif bulk_cred:
                device.credential_id = int(bulk_cred)
            bulk_enabled = data.get("bulk_enabled", "")
            if bulk_enabled == "1":
                device.enabled = True
            elif bulk_enabled == "0":
                device.enabled = False
        db.commit()

    return Redirect(path="/devices")


@get("/{device_id:int}/edit", dependencies={"db": provide_db})
async def edit_device(device_id: int, db: Session) -> Template:
    device = db.get(Device, device_id)
    return Template(
        template_name="devices/form.html",
        context=_device_form_context(db, device),
    )


@post("/{device_id:int}", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER)
async def update_device(
    device_id: int,
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    device = db.get(Device, device_id)
    device.name = data["name"]
    device.hostname = data["hostname"]
    device.port = int(data["port"]) if data.get("port") else None
    device.description = data.get("description") or None
    device.group_id = int(data["group_id"])
    device.profile_id = int(data["profile_id"])
    device.credential_id = int(data["credential_id"]) if data.get("credential_id") else None
    device.enabled = bool(data.get("enabled"))
    db.commit()
    return Redirect(path="/devices")


@post("/{device_id:int}/delete", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER)
async def delete_device(device_id: int, db: Session) -> Redirect:
    device = db.get(Device, device_id)
    if device:
        db.delete(device)
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
        bulk_devices,
        edit_device,
        update_device,
        delete_device,
        import_form,
        import_template,
        import_submit,
    ],
)
