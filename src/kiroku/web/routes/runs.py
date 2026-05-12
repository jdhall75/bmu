import json

from jinja2.sandbox import SandboxedEnvironment
from litestar import Router, get
from litestar.response import Template
from sqlalchemy import select
from sqlalchemy.orm import Session

from kiroku.models import Run, RunBatch
from kiroku.web.deps import provide_db

_sandbox = SandboxedEnvironment(autoescape=False)


@get("/", dependencies={"db": provide_db})
async def list_batches(db: Session) -> Template:
    batches = db.scalars(
        select(RunBatch).order_by(RunBatch.started_at.desc()).limit(100)
    ).all()
    return Template(template_name="runs/batches.html", context={"batches": batches})


@get("/batches/{batch_id:int}", dependencies={"db": provide_db})
async def view_batch(batch_id: int, db: Session) -> Template:
    batch = db.get(RunBatch, batch_id)
    runs = db.scalars(
        select(Run).where(Run.batch_id == batch_id).order_by(Run.device_id)
    ).all()
    return Template(template_name="runs/batch_detail.html", context={"batch": batch, "runs": runs})


@get("/batches/{batch_id:int}/live", dependencies={"db": provide_db})
async def batch_live_fragment(batch_id: int, db: Session) -> Template:
    batch = db.get(RunBatch, batch_id)
    runs = db.scalars(
        select(Run).where(Run.batch_id == batch_id).order_by(Run.device_id)
    ).all()
    return Template(template_name="runs/_batch_live.html", context={"batch": batch, "runs": runs})


@get("/batches/{batch_id:int}/row", dependencies={"db": provide_db})
async def batch_row_fragment(batch_id: int, db: Session) -> Template:
    batch = db.get(RunBatch, batch_id)
    return Template(template_name="runs/_batch_row.html", context={"b": batch})


@get("/{run_id:int}", dependencies={"db": provide_db})
async def view_run(run_id: int, db: Session) -> Template:
    run = db.get(Run, run_id)
    jinja2_template = (
        run.parser_template.jinja2_template
        if run and run.parser_template
        else None
    )
    parsed_display = _parsed_display(run.parsed_data if run else None, jinja2_template)
    return Template(
        template_name="runs/detail.html",
        context={"run": run, "parsed_display": parsed_display},
    )


def _parsed_display(data: list | dict | None, jinja2_template: str | None = None) -> dict | None:
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


router = Router(
    path="/runs",
    route_handlers=[
        list_batches,
        view_batch,
        batch_live_fragment,
        batch_row_fragment,
        view_run,
    ],
)
