from litestar import Router, get, post
from litestar.params import Body
from litestar.enums import RequestEncodingType
from litestar.response import Redirect, Template
from sqlalchemy import select
from sqlalchemy.orm import Session

from bmu.models import ParserTemplate, Profile, ProfileKind, TransportProtocol
from bmu.web.deps import provide_db

# Common scrapli platforms; "generic" is the GenericDriver fallback.
SCRAPLI_PLATFORMS = [
    "generic",
    "cisco_iosxe",
    "cisco_iosxr",
    "cisco_nxos",
    "cisco_asa",
    "arista_eos",
    "juniper_junos",
    "huawei_vrp",
]


@get("/", dependencies={"db": provide_db})
async def list_profiles(db: Session) -> Template:
    profiles = db.scalars(select(Profile).order_by(Profile.name)).all()
    return Template(template_name="profiles/list.html", context={"profiles": profiles})


@get("/new", dependencies={"db": provide_db})
async def new_profile(db: Session) -> Template:
    return Template(
        template_name="profiles/form.html",
        context={
            "profile": None,
            "platforms": SCRAPLI_PLATFORMS,
            "transports": [t.value for t in TransportProtocol],
            "kinds": [k.value for k in ProfileKind],
            "parsers": db.scalars(select(ParserTemplate).order_by(ParserTemplate.name)).all(),
        },
    )


@post("/", dependencies={"db": provide_db})
async def create_profile(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    p = Profile(
        name=data["name"],
        description=data.get("description") or None,
        kind=ProfileKind(data["kind"]),
        platform=data.get("platform") or None,
        transport=TransportProtocol(data["transport"]) if data.get("transport") else None,
        port=int(data["port"]) if data.get("port") else None,
        prompt_pattern=data.get("prompt_pattern") or None,
        pre_commands=data.get("pre_commands") or None,
        disable_paging_command=data.get("disable_paging_command") or None,
        commands=data.get("commands") or None,
        manufacturer=data.get("manufacturer") or None,
        rpc=data.get("rpc") or None,
        parser_template_id=int(data["parser_template_id"])
        if data.get("parser_template_id")
        else None,
    )
    db.add(p)
    db.commit()
    return Redirect(path="/profiles")


router = Router(path="/profiles", route_handlers=[list_profiles, new_profile, create_profile])
