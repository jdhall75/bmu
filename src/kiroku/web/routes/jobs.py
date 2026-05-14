from litestar import Router, get, post
from litestar.params import Body
from litestar.enums import RequestEncodingType
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER
from sqlalchemy import select
from sqlalchemy.orm import Session

from kiroku.dispatch import fire_job
from kiroku.models import Device, DeviceGroup, Job, JobKind, ParserTemplate, Run, RunStatus
from kiroku.web.deps import provide_db
from kiroku.web.helpers import parse_ids, sandbox as _sandbox


def _job_form_context(db: Session, job=None) -> dict:
    return {
        "job": job,
        "kinds": [k.value for k in JobKind],
        "parsers": db.scalars(
            select(ParserTemplate).order_by(ParserTemplate.name)
        ).all(),
        "device_groups": db.scalars(
            select(DeviceGroup).order_by(DeviceGroup.name)
        ).all(),
        "devices": db.scalars(select(Device).order_by(Device.name)).all(),
    }


def _apply_job_data(job: Job, data: dict, db: Session) -> None:
    job.name = data["name"]
    job.description = data.get("description") or None
    job.kind = JobKind(data["kind"])
    job.commands = data.get("commands") or None
    job.rpc = data.get("rpc") or None
    job.parser_template_id = (
        int(data["parser_template_id"]) if data.get("parser_template_id") else None
    )
    job.cve_vendor = data.get("cve_vendor") or None
    job.cve_product = data.get("cve_product") or None
    job.show_on_device = data.get("show_on_device") == "1"

    group_ids = parse_ids(data, "device_group_ids")
    device_ids = parse_ids(data, "device_ids")

    job.device_groups = (
        db.scalars(select(DeviceGroup).where(DeviceGroup.id.in_(group_ids))).all()
        if group_ids
        else []
    )

    job.devices = (
        db.scalars(select(Device).where(Device.id.in_(device_ids))).all()
        if device_ids
        else []
    )


@get("/", dependencies={"db": provide_db})
async def list_jobs(db: Session) -> Template:
    jobs = db.scalars(select(Job).order_by(Job.name)).all()
    return Template(template_name="jobs/list.html", context={"jobs": jobs})


@get("/new", dependencies={"db": provide_db})
async def new_job(db: Session) -> Template:
    return Template(
        template_name="jobs/form.html",
        context=_job_form_context(db),
    )


@post("/", dependencies={"db": provide_db})
async def create_job(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    j = Job()
    _apply_job_data(j, data, db)
    db.add(j)
    db.commit()
    return Redirect(path="/jobs")


@post("/bulk", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER)
async def bulk_jobs(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    ids = parse_ids(data)
    if ids and data.get("action") == "delete":
        for job in db.scalars(select(Job).where(Job.id.in_(ids))).all():
            db.delete(job)
        db.commit()
    return Redirect(path="/jobs")


@get("/{job_id:int}/edit", dependencies={"db": provide_db})
async def edit_job(job_id: int, db: Session) -> Template:
    job = db.get(Job, job_id)
    return Template(
        template_name="jobs/form.html",
        context=_job_form_context(db, job),
    )


@post("/{job_id:int}", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER)
async def update_job(
    job_id: int,
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    job = db.get(Job, job_id)
    _apply_job_data(job, data, db)
    db.commit()
    return Redirect(path="/jobs")


@post(
    "/{job_id:int}/delete",
    dependencies={"db": provide_db},
    status_code=HTTP_303_SEE_OTHER,
)
async def delete_job(job_id: int, db: Session) -> Redirect:
    job = db.get(Job, job_id)
    if job:
        db.delete(job)
        db.commit()
    return Redirect(path="/jobs")


@post(
    "/{job_id:int}/run", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER
)
async def run_job_adhoc(job_id: int, db: Session) -> Redirect:
    job = db.get(Job, job_id)
    if job is None:
        return Redirect(path="/jobs")
    batch = fire_job(job, db)
    return Redirect(path=f"/runs/batches/{batch.id}")


@get("/{job_id:int}/data", dependencies={"db": provide_db})
async def job_data(job_id: int, db: Session) -> Template:
    job = db.get(Job, job_id)
    if job is None:
        return Redirect(path="/jobs")

    # Union of explicitly selected devices + all devices from assigned groups
    device_map: dict[int, Device] = {d.id: d for d in job.devices}
    for group in job.device_groups:
        for d in group.devices:
            device_map.setdefault(d.id, d)
    devices_in_scope = sorted(device_map.values(), key=lambda d: d.name)

    # All successful runs for this job that produced parsed_data, newest first
    all_runs = db.scalars(
        select(Run)
        .where(
            Run.job_id == job_id,
            Run.status == RunStatus.SUCCESS,
            Run.parsed_data.is_not(None),
        )
        .order_by(Run.device_id, Run.finished_at.desc())
    ).all()

    # Keep only the latest run per device
    latest_by_device: dict[int, Run] = {}
    for run in all_runs:
        if run.device_id not in latest_by_device:
            latest_by_device[run.device_id] = run

    # Ordered column headers: union of all dict keys in first-seen order
    headers: list[str] = []
    seen_keys: set[str] = set()
    for device in devices_in_scope:
        run = latest_by_device.get(device.id)
        if run and isinstance(run.parsed_data, list):
            for row in run.parsed_data:
                if isinstance(row, dict):
                    for key in row.keys():
                        if key not in seen_keys:
                            headers.append(key)
                            seen_keys.add(key)

    # Per-device row data for the default table
    device_rows = []
    for device in devices_in_scope:
        run = latest_by_device.get(device.id)
        data_rows = []
        if run and isinstance(run.parsed_data, list):
            data_rows = [r for r in run.parsed_data if isinstance(r, dict)]
        device_rows.append({"device": device, "run": run, "rows": data_rows})

    # Context for aggregate_template: flat rows + structured devices list
    flat_rows = []
    for item in device_rows:
        for row in item["rows"]:
            flat_rows.append({"device": item["device"].name, **row})

    agg_devices = [
        {
            "name": item["device"].name,
            "id": item["device"].id,
            "collected_at": item["run"].finished_at if item["run"] else None,
            "rows": item["rows"],
        }
        for item in device_rows
    ]

    # Render aggregate_template if the parser has one
    aggregate_tmpl = (
        job.parser_template.aggregate_template if job.parser_template else None
    )
    aggregate_html = None
    aggregate_error = None
    if aggregate_tmpl:
        try:
            aggregate_html = _sandbox.from_string(aggregate_tmpl).render(
                rows=flat_rows,
                headers=headers,
                devices=agg_devices,
                job=job,
            )
        except Exception as exc:
            aggregate_error = f"{type(exc).__name__}: {exc}"

    return Template(
        template_name="jobs/data.html",
        context={
            "job": job,
            "device_rows": device_rows,
            "headers": headers,
            "aggregate_html": aggregate_html,
            "aggregate_error": aggregate_error,
        },
    )


router = Router(
    path="/jobs",
    route_handlers=[
        list_jobs,
        new_job,
        create_job,
        bulk_jobs,
        edit_job,
        update_job,
        delete_job,
        run_job_adhoc,
        job_data,
    ],
)
