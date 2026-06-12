import json
from datetime import datetime, timezone

from litestar import Router, get, post
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER
from sqlalchemy import select
from sqlalchemy.orm import Session

from kiroku.config import get_settings
from kiroku.models import Run, RunBatch, RunStatus
from kiroku.queue import job_stream_names, purge_undelivered
from kiroku.recorder.git_store import GitStore
from kiroku.web.auth import require_admin, require_authenticated
from kiroku.web.deps import provide_db
from kiroku.web.helpers import sandbox as _sandbox
from kiroku.web.redir import redir


def _changed_run_ids(runs: list[Run], commit_sha: str) -> set[int]:
    """Return run IDs whose device config was part of the given git commit."""
    try:
        store = GitStore()
        changed_paths = set(store.changed_files(commit_sha))
    except Exception:
        return set()
    if not changed_paths:
        return set()
    result: set[int] = set()
    for run in runs:
        if not run.device:
            continue
        groups = run.device.groups or []
        group_name = groups[0].name if groups else "ungrouped"
        try:
            rel = store.file_path(group=group_name, device=run.device.name)
            if rel in changed_paths:
                result.add(run.id)
        except Exception:
            pass
    return result


_KINDS = ("backup", "collect", "cve_scan")


@get("/", dependencies={"db": provide_db})
async def list_batches(
    db: Session,
    q: str = "",
    kind: str = "",
    status: str = "",
) -> Template:
    stmt = select(RunBatch).order_by(RunBatch.started_at.desc())
    if q:
        stmt = stmt.where(RunBatch.schedule_name.ilike(f"%{q}%"))
    if kind:
        stmt = stmt.where(RunBatch.kind == kind)
    if status == "running":
        stmt = stmt.where((RunBatch.succeeded + RunBatch.failed) < RunBatch.total)
    elif status == "failed":
        stmt = stmt.where(RunBatch.failed > 0)
    elif status == "success":
        stmt = stmt.where(RunBatch.succeeded == RunBatch.total, RunBatch.failed == 0)
    elif status == "complete":
        stmt = stmt.where((RunBatch.succeeded + RunBatch.failed) >= RunBatch.total)
    batches = db.scalars(stmt.limit(200)).all()
    return Template(
        template_name="runs/batches.html",
        context={
            "batches": batches,
            "q": q,
            "kind": kind,
            "status": status,
            "kinds": _KINDS,
            "has_filters": bool(q or kind or status),
        },
    )


@get("/batches/{batch_id:int}", dependencies={"db": provide_db})
async def view_batch(batch_id: int, db: Session) -> Template:
    batch = db.get(RunBatch, batch_id)
    runs = db.scalars(
        select(Run).where(Run.batch_id == batch_id).order_by(Run.device_id)
    ).all()
    changed_run_ids: set[int] = set()
    if batch and batch.commit_sha and batch.kind == "backup":
        changed_run_ids = _changed_run_ids(list(runs), batch.commit_sha)
    return Template(
        template_name="runs/batch_detail.html",
        context={"batch": batch, "runs": runs, "changed_run_ids": changed_run_ids},
    )


@get("/batches/{batch_id:int}/live", dependencies={"db": provide_db})
async def batch_live_fragment(batch_id: int, db: Session) -> Template:
    batch = db.get(RunBatch, batch_id)
    runs = db.scalars(
        select(Run).where(Run.batch_id == batch_id).order_by(Run.device_id)
    ).all()
    changed_run_ids: set[int] = set()
    if batch and batch.commit_sha and batch.kind == "backup":
        changed_run_ids = _changed_run_ids(list(runs), batch.commit_sha)
    return Template(
        template_name="runs/_batch_live.html",
        context={"batch": batch, "runs": runs, "changed_run_ids": changed_run_ids},
    )


@get("/batches/{batch_id:int}/row", dependencies={"db": provide_db})
async def batch_row_fragment(batch_id: int, db: Session) -> Template:
    batch = db.get(RunBatch, batch_id)
    return Template(template_name="runs/_batch_row.html", context={"b": batch})


@get("/{run_id:int}", dependencies={"db": provide_db})
async def view_run(run_id: int, db: Session) -> Template:
    run = db.get(Run, run_id)
    jinja2_template = (
        run.parser_template.jinja2_template if run and run.parser_template else None
    )
    parsed_display = _parsed_display(run.parsed_data if run else None, jinja2_template)
    return Template(
        template_name="runs/detail.html",
        context={"run": run, "parsed_display": parsed_display},
    )


def _parsed_display(
    data: list | dict | None, jinja2_template: str | None = None
) -> dict | None:
    if data is None:
        return None
    if jinja2_template:
        try:
            rows = data if isinstance(data, list) else [data]
            headers = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []
            html = _sandbox.from_string(jinja2_template).render(
                data=data, rows=rows, headers=headers
            )
            return {"type": "jinja2", "html": html}
        except Exception as exc:
            return {"type": "jinja2_error", "error": f"{type(exc).__name__}: {exc}"}
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return {"type": "table", "headers": list(data[0].keys()), "rows": data}
    return {"type": "json", "value": json.dumps(data, indent=2)}


@post(
    "/purge-queue",
    dependencies={"db": provide_db},
    status_code=HTTP_303_SEE_OTHER,
    guards=[require_admin],
)
async def purge_queue(db: Session) -> Redirect:
    settings = get_settings()
    now = datetime.now(tz=timezone.utc)

    purged: list[tuple[str, int]] = []
    for stream in job_stream_names():
        purged.extend(purge_undelivered(stream, settings.job_consumer_group))

    if purged:
        run_ids = {run_id for _, run_id in purged}
        runs = db.scalars(select(Run).where(Run.id.in_(run_ids))).all()
        batch_cancelled: dict[int, int] = {}
        for run in runs:
            if run.status in (RunStatus.PENDING, RunStatus.RUNNING):
                run.status = RunStatus.CANCELLED
                run.finished_at = now
                if run.batch_id:
                    batch_cancelled[run.batch_id] = batch_cancelled.get(run.batch_id, 0) + 1

        for batch_id, count in batch_cancelled.items():
            batch = db.get(RunBatch, batch_id)
            if batch:
                batch.failed += count
                if batch.finished_at is None and (batch.succeeded + batch.failed) >= batch.total:
                    batch.finished_at = now

        db.commit()

    return redir("/runs")


@post(
    "/batches/{batch_id:int}/cancel",
    dependencies={"db": provide_db},
    status_code=HTTP_303_SEE_OTHER,
    guards=[require_admin],
)
async def cancel_batch(batch_id: int, db: Session) -> Redirect:
    batch = db.get(RunBatch, batch_id)
    if batch and batch.finished_at is None:
        now = datetime.now(tz=timezone.utc)
        pending = db.scalars(
            select(Run).where(
                Run.batch_id == batch_id,
                Run.status.in_([RunStatus.PENDING, RunStatus.RUNNING]),
            )
        ).all()
        for run in pending:
            run.status = RunStatus.CANCELLED
            run.finished_at = now
            batch.failed += 1
        if (batch.succeeded + batch.failed) >= batch.total:
            batch.finished_at = now
        db.commit()
    return redir(f"/runs/batches/{batch_id}")


router = Router(
    path="/runs",
    guards=[require_authenticated],
    route_handlers=[
        list_batches,
        view_batch,
        batch_live_fragment,
        batch_row_fragment,
        view_run,
        purge_queue,
        cancel_batch,
    ],
)
