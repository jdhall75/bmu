from __future__ import annotations

from pydantic import BaseModel

from litestar import Router, get, post
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER
from sqlalchemy import select
from sqlalchemy.orm import Session

from kiroku.models import ParserTemplate, ParserType
from kiroku.web.deps import provide_db


def _parse_ids(data: dict) -> list[int]:
    raw = data.get("ids", [])
    if isinstance(raw, str):
        raw = [raw]
    return [int(i) for i in raw if i]


def _form_context(db: Session, parser=None) -> dict:
    return {
        "parser": parser,
        "types": [t.value for t in ParserType],
    }


@get("/", dependencies={"db": provide_db})
async def list_parsers(db: Session) -> Template:
    parsers = db.scalars(select(ParserTemplate).order_by(ParserTemplate.name)).all()
    return Template("parsers/list.html", context={"parsers": parsers})


@get("/new", dependencies={"db": provide_db})
async def new_parser(db: Session) -> Template:
    return Template("parsers/form.html", context=_form_context(db))


@post("/", dependencies={"db": provide_db})
async def create_parser(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    p = ParserTemplate(
        name=data["name"],
        description=data.get("description") or None,
        type=ParserType(data["type"]),
        body=data["body"],
        jinja2_template=data.get("jinja2_template") or None,
    )
    db.add(p)
    db.commit()
    return Redirect(path="/parsers")


@post("/bulk", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER)
async def bulk_parsers(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    ids = _parse_ids(data)
    if ids and data.get("action") == "delete":
        for p in db.scalars(select(ParserTemplate).where(ParserTemplate.id.in_(ids))).all():
            db.delete(p)
        db.commit()
    return Redirect(path="/parsers")


@get("/{parser_id:int}/edit", dependencies={"db": provide_db})
async def edit_parser(parser_id: int, db: Session) -> Template:
    parser = db.get(ParserTemplate, parser_id)
    return Template("parsers/form.html", context=_form_context(db, parser))


@post("/{parser_id:int}", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER)
async def update_parser(
    parser_id: int,
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    parser = db.get(ParserTemplate, parser_id)
    parser.name = data["name"]
    parser.description = data.get("description") or None
    parser.type = ParserType(data["type"])
    parser.body = data["body"]
    parser.jinja2_template = data.get("jinja2_template") or None
    db.commit()
    return Redirect(path="/parsers")


@post("/{parser_id:int}/delete", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER)
async def delete_parser(parser_id: int, db: Session) -> Redirect:
    parser = db.get(ParserTemplate, parser_id)
    if parser:
        db.delete(parser)
        db.commit()
    return Redirect(path="/parsers")


# ---------------------------------------------------------------------------
# Test bed
# ---------------------------------------------------------------------------


@get("/test", dependencies={"db": provide_db})
async def test_bed(db: Session) -> Template:
    parsers = db.scalars(select(ParserTemplate).order_by(ParserTemplate.name)).all()
    return Template("parsers/test.html", context={"parsers": parsers})


class _TestRequest(BaseModel):
    type: str
    input: str
    template: str


@post("/test/run", status_code=200)
async def run_test(data: _TestRequest) -> dict:
    from kiroku.worker.parsers import parse
    try:
        result = parse(data.type, data.template, data.input)
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


router = Router(
    path="/parsers",
    route_handlers=[
        list_parsers,
        new_parser,
        create_parser,
        bulk_parsers,
        edit_parser,
        update_parser,
        delete_parser,
        test_bed,
        run_test,
    ],
)
