from litestar import Router, get, post
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER
from sqlalchemy import select
from sqlalchemy.orm import Session

from kiroku.models import Platform
from kiroku.web.auth import require_admin, require_authenticated
from kiroku.web.deps import provide_db
from kiroku.web.redir import redir

# Shown in the form as a reference when the operator creates a new platform.
EXAMPLE_YAML = """\
# Nokia SR Linux example — adapt for your platform.
#
# prompt_pattern  : top-level regex that matches any prompt in any mode.
# default_mode    : the mode the device starts in after login.
# modes           : list of named modes, each with its own prompt_pattern
#                   and instructions to reach other modes.
# failure_indicators : strings that signal a failed command.
# on_open_instructions  : sent once after login.
# on_close_instructions : sent once before disconnect.
#
# Instruction types:
#   send_input:  { input: "command" }
#   enter_mode:  { requested_mode: "mode-name" }
#   write:       { input: "raw-text" }   # no prompt wait

prompt_pattern: '(^.*[>#$]\\s?+$)'
default_mode: 'exec'
modes:
  - name: 'exec'
    prompt_pattern: '^.*[>#$]\\s?+$'
    accessible_modes:
      - name: 'configuration'
        instructions:
          - send_input:
              input: 'configure'
  - name: 'configuration'
    prompt_pattern: '^.*\\(config\\)[>#$]\\s?+$'
    accessible_modes:
      - name: 'exec'
        instructions:
          - send_input:
              input: 'exit'
failure_indicators:
  - 'Error:'
  - 'Invalid input'
on_open_instructions:
  - enter_mode:
      requested_mode: 'exec'
on_close_instructions:
  - enter_mode:
      requested_mode: 'exec'
  - write:
      input: 'exit'
"""


@get("/", dependencies={"db": provide_db})
async def list_platforms(db: Session) -> Template:
    platforms = db.scalars(select(Platform).order_by(Platform.name)).all()
    return Template(
        template_name="platforms/list.html",
        context={"platforms": platforms},
    )


@get("/new")
async def new_platform() -> Template:
    return Template(
        template_name="platforms/form.html",
        context={"platform": None, "example_yaml": EXAMPLE_YAML},
    )


@post("/", dependencies={"db": provide_db}, guards=[require_admin])
async def create_platform(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    p = Platform(
        name=data["name"],
        description=data.get("description") or None,
        yaml_body=data["yaml_body"],
    )
    db.add(p)
    db.commit()
    return redir("/platforms")


@get("/{platform_id:int}/edit", dependencies={"db": provide_db})
async def edit_platform(platform_id: int, db: Session) -> Template:
    platform = db.get(Platform, platform_id)
    return Template(
        template_name="platforms/form.html",
        context={"platform": platform, "example_yaml": EXAMPLE_YAML},
    )


@post(
    "/{platform_id:int}",
    dependencies={"db": provide_db},
    status_code=HTTP_303_SEE_OTHER,
    guards=[require_admin],
)
async def update_platform(
    platform_id: int,
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    platform = db.get(Platform, platform_id)
    if not platform:
        return redir("/platforms")
    platform.name = data["name"]
    platform.description = data.get("description") or None
    platform.yaml_body = data["yaml_body"]
    db.commit()
    return redir("/platforms")


@post(
    "/{platform_id:int}/delete",
    dependencies={"db": provide_db},
    status_code=HTTP_303_SEE_OTHER,
    guards=[require_admin],
)
async def delete_platform(platform_id: int, db: Session) -> Redirect:
    platform = db.get(Platform, platform_id)
    if platform:
        db.delete(platform)
        db.commit()
    return redir("/platforms")


router = Router(
    path="/platforms",
    guards=[require_authenticated],
    route_handlers=[
        list_platforms,
        new_platform,
        create_platform,
        edit_platform,
        update_platform,
        delete_platform,
    ],
)
