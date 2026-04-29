from litestar import Router, get
from litestar.response import Template
from sqlalchemy import select
from sqlalchemy.orm import Session

from bmu.models import Run
from bmu.web.deps import provide_db


@get("/", dependencies={"db": provide_db})
async def list_runs(db: Session) -> Template:
    runs = db.scalars(select(Run).order_by(Run.created_at.desc()).limit(200)).all()
    return Template(template_name="runs/list.html", context={"runs": runs})


@get("/{run_id:int}", dependencies={"db": provide_db})
async def view_run(db: Session, run_id: int) -> Template:
    run = db.get(Run, run_id)
    return Template(template_name="runs/detail.html", context={"run": run})


router = Router(path="/runs", route_handlers=[list_runs, view_run])
