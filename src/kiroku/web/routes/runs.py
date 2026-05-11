from litestar import Router, get
from litestar.response import Template
from sqlalchemy import select
from sqlalchemy.orm import Session

from kiroku.models import Run, RunBatch
from kiroku.web.deps import provide_db


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
    return Template(template_name="runs/detail.html", context={"run": run})


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
