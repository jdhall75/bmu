import threading
import time
import uuid

from litestar import Router, get, post
from litestar.background_tasks import BackgroundTask
from litestar.connection import Request
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Redirect, Response, Template
from litestar.status_codes import HTTP_303_SEE_OTHER
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from kiroku.config import get_settings
from kiroku.db import SessionLocal
from kiroku.models import (
    Credential,
    CveScan,
    Device,
    DeviceGroup,
    DriverKind,
    Job,
    Platform,
    Run,
    RunStatus,
    TransportProtocol,
)
from kiroku.web.auth import require_admin, require_authenticated
from kiroku.web.deps import provide_db
from kiroku.web.helpers import parse_ids, worker_pools as _worker_pools
from kiroku.web.import_devices import import_csv
from kiroku.web.routes.runs import _parsed_display

# ---------------------------------------------------------------------------
# In-process import task store (single-worker; no Redis dependency needed)
# ---------------------------------------------------------------------------

_import_tasks: dict[str, dict] = {}
_import_tasks_lock = threading.Lock()
_TASK_TTL = 600.0  # 10 minutes


def _set_task(task_id: str, data: dict) -> None:
    with _import_tasks_lock:
        _import_tasks[task_id] = {**data, "_ts": time.monotonic()}


def _get_task(task_id: str) -> dict | None:
    with _import_tasks_lock:
        task = _import_tasks.get(task_id)
    if task is None:
        return None
    if time.monotonic() - task.get("_ts", 0) > _TASK_TTL:
        with _import_tasks_lock:
            _import_tasks.pop(task_id, None)
        return None
    return task


def _prune_tasks() -> None:
    cutoff = time.monotonic() - _TASK_TTL
    with _import_tasks_lock:
        expired = [k for k, v in _import_tasks.items() if v.get("_ts", 0) < cutoff]
        for k in expired:
            del _import_tasks[k]


def _run_import_bg(task_id: str, raw: str) -> None:
    _set_task(task_id, {"status": "running"})
    db = SessionLocal()
    try:
        results, created, updated = import_csv(db, raw)
        _set_task(task_id, {
            "status": "done",
            "results": [
                {"line": r.line, "name": r.name, "ok": r.ok,
                 "message": r.message, "action": r.action}
                for r in results
            ],
            "created": created,
            "updated": updated,
            "error": None,
        })
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        _set_task(task_id, {
            "status": "error",
            "results": [],
            "created": 0,
            "updated": 0,
            "error": f"{type(exc).__name__}: {exc}",
        })
    finally:
        try:
            db.close()
        except Exception:
            pass
    _prune_tasks()

_SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
_PAGE_SIZE = 100

# Built-in scrapli platform names.
SCRAPLI_PLATFORMS = [
    "cisco_iosxe",
    "cisco_iosxr",
    "cisco_nxos",
    "cisco_asa",
    "arista_eos",
    "juniper_junos",
]


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
    "name,hostname,port,description,make,model,role,group,platform,transport,driver_kind,credentials,enabled,worker_pool\n"
    "edge-rtr-01,10.0.0.1,22,Core edge router,Cisco,ASR-9000,edge,core,cisco_iosxe,ssh,cli,core-admin,1,\n"
)


def _platform_value(device) -> str:
    """Return the combined platform select value for an existing device."""
    if device and device.custom_platform_id:
        return f"custom:{device.custom_platform_id}"
    if device and device.platform:
        return f"builtin:{device.platform}"
    return ""


def _device_form_options(db: Session) -> dict:
    return {
        "groups": db.scalars(select(DeviceGroup).order_by(DeviceGroup.name)).all(),
        "credentials": db.scalars(select(Credential).order_by(Credential.name)).all(),
        "builtin_platforms": SCRAPLI_PLATFORMS,
        "custom_platforms": db.scalars(select(Platform).order_by(Platform.name)).all(),
        "transports": [t.value for t in TransportProtocol],
        "driver_kinds": [k.value for k in DriverKind],
        "worker_pools": _worker_pools(db),
    }


def _device_form_context(db: Session, device=None) -> dict:
    settings = get_settings()
    return {
        "device": device,
        "platform_value": _platform_value(device),
        "default_connect_timeout": settings.worker_connect_timeout,
        "default_command_timeout": settings.worker_command_timeout,
        **_device_form_options(db),
    }


def _apply_platform(device: Device, data: dict) -> None:
    """Parse the combined platform_value and set device.platform / custom_platform_id."""
    pv = data.get("platform_value", "")
    if pv.startswith("builtin:"):
        device.platform = pv[len("builtin:") :]
        device.custom_platform_id = None
    elif pv.startswith("custom:"):
        device.custom_platform_id = int(pv[len("custom:") :])
        device.platform = None
    else:
        device.platform = None
        device.custom_platform_id = None


def _build_filter_qs(
    q: str, group_id: str, make_filter: str, role_filter: str, enabled_filter: str
) -> str:
    parts = []
    if q:
        parts.append(f"q={q}")
    if group_id:
        parts.append(f"group_id={group_id}")
    if make_filter:
        parts.append(f"make={make_filter}")
    if role_filter:
        parts.append(f"role={role_filter}")
    if enabled_filter:
        parts.append(f"enabled={enabled_filter}")
    return "&".join(parts)


@get("/", dependencies={"db": provide_db})
async def list_devices(
    db: Session,
    page: int = 1,
    q: str = "",
    group_id: str = "",
    make: str = "",
    role: str = "",
    enabled: str = "",
) -> Template:
    page = max(1, page)

    base = select(Device).options(selectinload(Device.groups))
    count_base = select(func.count()).select_from(Device)

    if q:
        like = f"%{q}%"
        filt = or_(Device.name.ilike(like), Device.hostname.ilike(like))
        base = base.where(filt)
        count_base = count_base.where(filt)
    if group_id:
        filt = Device.groups.any(DeviceGroup.id == int(group_id))
        base = base.where(filt)
        count_base = count_base.where(filt)
    if make:
        filt = Device.make.ilike(f"%{make}%")
        base = base.where(filt)
        count_base = count_base.where(filt)
    if role:
        filt = Device.role.ilike(f"%{role}%")
        base = base.where(filt)
        count_base = count_base.where(filt)
    if enabled in ("1", "0"):
        filt = Device.enabled == (enabled == "1")
        base = base.where(filt)
        count_base = count_base.where(filt)

    total = db.scalar(count_base) or 0
    total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = min(page, total_pages)
    offset = (page - 1) * _PAGE_SIZE

    devices = db.scalars(
        base.order_by(Device.name).offset(offset).limit(_PAGE_SIZE)
    ).all()

    has_filters = any([q, group_id, make, role, enabled])
    filter_qs = _build_filter_qs(q, group_id, make, role, enabled)

    return Template(
        template_name="devices/list.html",
        context={
            "devices": devices,
            "cve_badges": _cve_badges(db),
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "q": q,
            "group_id": group_id,
            "make_filter": make,
            "role_filter": role,
            "enabled_filter": enabled,
            "has_filters": has_filters,
            "filter_qs": filter_qs,
            **_device_form_options(db),
        },
    )


@get("/report", dependencies={"db": provide_db})
async def device_report(db: Session) -> Template:
    rows = db.execute(
        select(
            Device.make,
            Device.model,
            func.count().label("total"),
            func.count(Device.latest_backup_at).label("backed_up"),
        )
        .group_by(Device.make, Device.model)
        .order_by(Device.make.nulls_last(), Device.model.nulls_last())
    ).all()
    return Template(
        template_name="devices/report.html",
        context={"rows": rows},
    )


@get("/new", dependencies={"db": provide_db})
async def new_device(db: Session) -> Template:
    return Template(
        template_name="devices/form.html",
        context=_device_form_context(db),
    )


@post("/", dependencies={"db": provide_db}, guards=[require_admin])
async def create_device(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    group_ids = parse_ids(data, "group_ids")
    d = Device(
        name=data["name"],
        hostname=data["hostname"],
        port=int(data["port"]) if data.get("port") else None,
        description=data.get("description") or None,
        make=data.get("make") or None,
        model=data.get("model") or None,
        role=data.get("role") or None,
        credential_id=int(data["credential_id"]) if data.get("credential_id") else None,
        transport=TransportProtocol(data["transport"])
        if data.get("transport")
        else None,
        driver_kind=DriverKind(data["driver_kind"])
        if data.get("driver_kind")
        else None,
        connect_timeout=int(data["connect_timeout"])
        if data.get("connect_timeout")
        else None,
        command_timeout=int(data["command_timeout"])
        if data.get("command_timeout")
        else None,
        worker_pool=data.get("worker_pool") or None,
        enabled=bool(data.get("enabled")),
    )
    _apply_platform(d, data)
    if group_ids:
        d.groups = list(
            db.scalars(select(DeviceGroup).where(DeviceGroup.id.in_(group_ids))).all()
        )
    db.add(d)
    db.commit()
    return Redirect(path="/devices")


@post("/bulk", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER, guards=[require_admin])
async def bulk_devices(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    ids = parse_ids(data)
    action = data.get("action")

    if not ids:
        return Redirect(path="/devices")

    if action == "delete":
        for device in db.scalars(select(Device).where(Device.id.in_(ids))).all():
            db.delete(device)
        db.commit()

    elif action == "edit":
        bulk_group_id = data.get("bulk_group_id")
        bulk_group = db.get(DeviceGroup, int(bulk_group_id)) if bulk_group_id else None
        for device in db.scalars(
            select(Device)
            .options(selectinload(Device.groups))
            .where(Device.id.in_(ids))
        ).all():
            if data.get("bulk_port"):
                device.port = int(data["bulk_port"])
            if bulk_group and bulk_group not in device.groups:
                device.groups.append(bulk_group)
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
            if data.get("bulk_make"):
                device.make = data["bulk_make"] or None
            if data.get("bulk_model"):
                device.model = data["bulk_model"] or None
            if data.get("bulk_role"):
                device.role = data["bulk_role"] or None
            if "bulk_worker_pool" in data:
                device.worker_pool = data["bulk_worker_pool"] or None
        db.commit()

    return Redirect(path="/devices")


@get("/{device_id:int}/edit", dependencies={"db": provide_db})
async def edit_device(device_id: int, db: Session) -> Template:
    device = db.get(Device, device_id)
    return Template(
        template_name="devices/form.html",
        context=_device_form_context(db, device),
    )


@post(
    "/{device_id:int}", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER, guards=[require_admin]
)
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
    device.make = data.get("make") or None
    device.model = data.get("model") or None
    device.role = data.get("role") or None
    device.credential_id = (
        int(data["credential_id"]) if data.get("credential_id") else None
    )
    device.transport = (
        TransportProtocol(data["transport"]) if data.get("transport") else None
    )
    device.driver_kind = (
        DriverKind(data["driver_kind"]) if data.get("driver_kind") else None
    )
    device.connect_timeout = (
        int(data["connect_timeout"]) if data.get("connect_timeout") else None
    )
    device.command_timeout = (
        int(data["command_timeout"]) if data.get("command_timeout") else None
    )
    device.worker_pool = data.get("worker_pool") or None
    _apply_platform(device, data)
    device.enabled = bool(data.get("enabled"))
    group_ids = parse_ids(data, "group_ids")
    device.groups = (
        list(db.scalars(select(DeviceGroup).where(DeviceGroup.id.in_(group_ids))).all())
        if group_ids
        else []
    )
    db.commit()
    return Redirect(path="/devices")


@post(
    "/{device_id:int}/delete",
    dependencies={"db": provide_db},
    status_code=HTTP_303_SEE_OTHER,
    guards=[require_admin],
)
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
        headers={
            "content-disposition": 'attachment; filename="kiroku-devices-template.csv"'
        },
    )


@post("/import", guards=[require_admin])
async def import_submit(request: Request) -> Redirect | Template:
    form = await request.form()
    upload = form.get("file")
    pasted = (form.get("pasted") or "").strip()

    raw = ""
    if hasattr(upload, "read"):
        content = await upload.read()
        if content:
            raw = content.decode("utf-8-sig", errors="replace")
    if not raw and pasted:
        raw = str(pasted)

    if not raw:
        return Template(
            template_name="devices/import.html",
            context={"error": "Provide a CSV file or paste CSV text."},
        )

    task_id = uuid.uuid4().hex[:16]
    _set_task(task_id, {"status": "pending"})
    return Redirect(
        path=f"/devices/import/status/{task_id}",
        status_code=HTTP_303_SEE_OTHER,
        background=BackgroundTask(_run_import_bg, task_id, raw),
    )


@get("/import/status/{task_id:str}")
async def import_status_page(task_id: str) -> Template:
    return Template(
        template_name="devices/import_status.html",
        context={"task_id": task_id},
    )


@get("/import/status/{task_id:str}/poll")
async def import_poll(task_id: str) -> Template:
    import json as _json

    task = _get_task(task_id)
    status = task.get("status", "unknown") if task else "expired"

    headers: dict[str, str] = {}
    if status not in ("pending", "running"):
        if task and not task.get("error") and (task.get("created") or task.get("updated")):
            msg = ""
            if task.get("created"):
                msg += f"Created {task['created']} device(s)"
            if task.get("created") and task.get("updated"):
                msg += ", "
            if task.get("updated"):
                msg += f"updated {task['updated']} device(s)"
            headers["HX-Trigger"] = _json.dumps({"showToast": {"message": msg, "kind": "ok"}})
        elif status == "error" or (task and task.get("error")):
            headers["HX-Trigger"] = _json.dumps({"showToast": {"message": "Import failed.", "kind": "bad"}})

    return Template(
        template_name="devices/_import_poll.html",
        context={"task_id": task_id, "task": task, "status": status},
        headers=headers,
    )


@get("/{device_id:int}", dependencies={"db": provide_db})
async def view_device(device_id: int, db: Session) -> Template:
    device = db.get(Device, device_id)
    recent_runs = db.scalars(
        select(Run)
        .where(Run.device_id == device_id)
        .order_by(Run.created_at.desc())
        .limit(10)
    ).all()

    show_jobs = db.scalars(
        select(Job).where(Job.show_on_device == True, Job.kind == "collect")
    ).all()

    pinned_data: list[dict] = []
    for job in show_jobs:
        latest_run = db.scalars(
            select(Run)
            .where(
                Run.device_id == device_id,
                Run.job_id == job.id,
                Run.status == RunStatus.SUCCESS,
                Run.parsed_data.is_not(None),
            )
            .order_by(Run.finished_at.desc())
            .limit(1)
        ).first()
        if latest_run:
            tmpl = job.parser_template.jinja2_template if job.parser_template else None
            display = _parsed_display(latest_run.parsed_data, tmpl)
            if display:
                pinned_data.append({"job": job, "run": latest_run, "display": display})

    return Template(
        template_name="devices/detail.html",
        context={
            "device": device,
            "recent_runs": recent_runs,
            "pinned_data": pinned_data,
        },
    )


@get("/{device_id:int}/config", dependencies={"db": provide_db})
async def view_config(device_id: int, db: Session, sha: str | None = None) -> Template:
    device = db.get(Device, device_id)
    content: str | None = None
    if device and device.latest_backup_path:
        if sha:
            from kiroku.recorder.git_store import GitStore

            content = GitStore().read_at(device.latest_backup_path, sha)
        else:
            path = get_settings().backup_repo_path / device.latest_backup_path
            if path.exists():
                content = path.read_text(encoding="utf-8", errors="replace")
    return Template(
        template_name="devices/config.html",
        context={"device": device, "content": content, "sha": sha},
    )


@get("/{device_id:int}/config/diff", dependencies={"db": provide_db})
async def view_config_diff(
    device_id: int,
    db: Session,
    from_sha: str,
    to_sha: str,
) -> Template:
    from kiroku.recorder.git_store import GitStore

    device = db.get(Device, device_id)
    diff_rows: list[dict] = []
    if device and device.latest_backup_path:
        diff_rows = GitStore().diff_commits(device.latest_backup_path, from_sha, to_sha)
    return Template(
        template_name="devices/config_diff.html",
        context={
            "device": device,
            "diff_rows": diff_rows,
            "from_sha": from_sha,
            "to_sha": to_sha,
        },
    )


@get("/{device_id:int}/config/history", dependencies={"db": provide_db})
async def view_config_history(device_id: int, db: Session) -> Template:
    device = db.get(Device, device_id)
    history: list[dict] = []
    if device and device.latest_backup_path:
        from kiroku.recorder.git_store import GitStore

        store = GitStore()
        history = store.history(device.latest_backup_path)
    return Template(
        template_name="devices/config_history.html",
        context={"device": device, "history": history},
    )


@get("/{device_id:int}/config/search", dependencies={"db": provide_db})
async def search_config_history(
    device_id: int, db: Session, q: str = "", regex: str = ""
) -> Template:
    import re

    from kiroku.recorder.git_store import GitStore

    device = db.get(Device, device_id)
    results: list[dict] = []
    error: str | None = None
    use_regex = regex == "1"
    if device and device.latest_backup_path and q.strip():
        try:
            results = GitStore().search_history(
                device.latest_backup_path, q.strip(), use_regex=use_regex
            )
        except re.error as exc:
            error = f"Invalid regex: {exc}"
    return Template(
        template_name="devices/config_search.html",
        context={
            "device": device,
            "q": q,
            "regex": regex,
            "results": results,
            "error": error,
            "has_filters": bool(q),
        },
    )


router = Router(
    path="/devices",
    guards=[require_authenticated],
    route_handlers=[
        list_devices,
        new_device,
        create_device,
        bulk_devices,
        device_report,
        view_device,
        edit_device,
        update_device,
        delete_device,
        import_form,
        import_template,
        import_submit,
        import_status_page,
        import_poll,
        view_config,
        view_config_diff,
        view_config_history,
        search_config_history,
    ],
)
