from litestar import Router, get, post
from litestar.params import Body
from litestar.enums import RequestEncodingType
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER
from sqlalchemy import select
from sqlalchemy.orm import Session

from bmu.models import ParserTemplate, Profile, ProfileKind, TransportProtocol
from bmu.web.deps import provide_db

# Core scrapli platforms (built into the scrapli package).
# "generic" triggers GenericDriver with manual prompt/paging overrides.
SCRAPLI_PLATFORMS = [
    "generic",
    "cisco_iosxe",
    "cisco_iosxr",
    "cisco_nxos",
    "cisco_asa",
    "arista_eos",
    "juniper_junos",
]

# Community platforms from scrapli-community; discovered automatically by scrapli.
# These use structured NetworkDriver definitions (privilege levels, on_open hooks)
# so pre_commands and disable_paging_command can usually be left empty.
COMMUNITY_PLATFORMS = [
    "aethra_atosnt",
    "alcatel_aos",
    "aruba_aoscx",
    "cisco_aireos",
    "cisco_cbs",
    "cisco_ftd",
    "cumulus_linux",
    "cumulus_vtysh",
    "datacom_dmos",
    "datacom_dmswitch",
    "dell_emc",
    "dlink_os",
    "edgecore_ecs",
    "eltex_esr",
    "fortinet_fortios",
    "fortinet_wlc",
    "hp_comware",
    "huawei_smartax",
    "huawei_vrp",
    "mikrotik_routeros",
    "nokia_srlinux",
    "nokia_sros",
    "paloalto_panos",
    "raisecom_ros",
    "ruckus_fastiron",
    "ruckus_unleashed",
    "siemens_roxii",
    "versa_flexvnf",
    "vyos_vyos",
    "zyxel_dslam",
]


@get("/", dependencies={"db": provide_db})
async def list_profiles(db: Session) -> Template:
    profiles = db.scalars(select(Profile).order_by(Profile.name)).all()
    return Template(template_name="profiles/list.html", context={"profiles": profiles})


def _profile_form_context(db: Session, profile=None) -> dict:
    return {
        "profile": profile,
        "platforms": SCRAPLI_PLATFORMS,
        "community_platforms": COMMUNITY_PLATFORMS,
        "transports": [t.value for t in TransportProtocol],
        "kinds": [k.value for k in ProfileKind],
        "parsers": db.scalars(select(ParserTemplate).order_by(ParserTemplate.name)).all(),
    }


def _apply_profile_data(p: Profile, data: dict) -> None:
    p.name = data["name"]
    p.description = data.get("description") or None
    p.kind = ProfileKind(data["kind"])
    p.platform = data.get("platform") or None
    p.transport = TransportProtocol(data["transport"]) if data.get("transport") else None
    p.port = int(data["port"]) if data.get("port") else None
    p.prompt_pattern = data.get("prompt_pattern") or None
    p.pre_commands = data.get("pre_commands") or None
    p.disable_paging_command = data.get("disable_paging_command") or None
    p.commands = data.get("commands") or None
    p.manufacturer = data.get("manufacturer") or None
    p.rpc = data.get("rpc") or None
    p.parser_template_id = int(data["parser_template_id"]) if data.get("parser_template_id") else None


@get("/new", dependencies={"db": provide_db})
async def new_profile(db: Session) -> Template:
    return Template(
        template_name="profiles/form.html",
        context=_profile_form_context(db),
    )


@post("/", dependencies={"db": provide_db})
async def create_profile(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    p = Profile()
    _apply_profile_data(p, data)
    db.add(p)
    db.commit()
    return Redirect(path="/profiles")


@get("/{profile_id:int}/edit", dependencies={"db": provide_db})
async def edit_profile(profile_id: int, db: Session) -> Template:
    profile = db.get(Profile, profile_id)
    return Template(
        template_name="profiles/form.html",
        context=_profile_form_context(db, profile),
    )


@post("/{profile_id:int}", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER)
async def update_profile(
    profile_id: int,
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    profile = db.get(Profile, profile_id)
    _apply_profile_data(profile, data)
    db.commit()
    return Redirect(path="/profiles")


@post("/{profile_id:int}/delete", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER)
async def delete_profile(profile_id: int, db: Session) -> Redirect:
    profile = db.get(Profile, profile_id)
    if profile:
        db.delete(profile)
        db.commit()
    return Redirect(path="/profiles")


router = Router(
    path="/profiles",
    route_handlers=[
        list_profiles,
        new_profile,
        create_profile,
        edit_profile,
        update_profile,
        delete_profile,
    ],
)
