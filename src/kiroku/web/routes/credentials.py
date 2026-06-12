from litestar import Router, get, post
from litestar.params import Body
from litestar.enums import RequestEncodingType
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from kiroku.credentials.local import LocalCredentialResolver
from kiroku.models import Credential, CredentialProvider
from kiroku.web.auth import require_admin, require_authenticated
from kiroku.web.deps import provide_db
from kiroku.web.helpers import parse_ids
from kiroku.web.redir import redir


def _cred_form_context(cred=None) -> dict:
    return {
        "credential": cred,
        "providers": [p.value for p in CredentialProvider],
    }


def _build_payload(provider: CredentialProvider, data: dict):
    if provider is not CredentialProvider.LOCAL:
        return None
    local = LocalCredentialResolver()
    secret = {
        "username": data.get("username"),
        "password": data.get("password") or None,
        "enable_password": data.get("enable_password") or None,
    }
    return local.encrypt({k: v for k, v in secret.items() if v is not None})


def _apply_default(cred: Credential, is_default: bool, db: Session) -> None:
    if is_default:
        db.execute(update(Credential).values(is_default=False))
        cred.is_default = True
    else:
        cred.is_default = False


@get("/", dependencies={"db": provide_db})
async def list_creds(db: Session) -> Template:
    creds = db.scalars(select(Credential).order_by(Credential.name)).all()
    return Template(
        template_name="credentials/list.html", context={"credentials": creds}
    )


@get("/new", guards=[require_admin])
async def new_cred() -> Template:
    return Template(
        template_name="credentials/form.html",
        context=_cred_form_context(),
    )


@post("/", dependencies={"db": provide_db}, guards=[require_admin])
async def create_cred(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    provider = CredentialProvider(data["provider"])
    cred = Credential(
        name=data["name"],
        description=data.get("description") or None,
        provider=provider,
        encrypted_payload=_build_payload(provider, data),
        ref=data.get("ref") or None,
        username=data.get("username") or None,
    )
    db.add(cred)
    db.flush()
    _apply_default(cred, bool(data.get("is_default")), db)
    db.commit()
    return redir("/credentials")


@post("/bulk", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER, guards=[require_admin])
async def bulk_creds(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    ids = parse_ids(data)
    if ids and data.get("action") == "delete":
        for cred in db.scalars(select(Credential).where(Credential.id.in_(ids))).all():
            db.delete(cred)
        db.commit()
    return redir("/credentials")


@get("/{cred_id:int}/edit", dependencies={"db": provide_db}, guards=[require_admin])
async def edit_cred(cred_id: int, db: Session) -> Template:
    cred = db.get(Credential, cred_id)
    return Template(
        template_name="credentials/form.html",
        context=_cred_form_context(cred),
    )


@post("/{cred_id:int}", dependencies={"db": provide_db}, status_code=HTTP_303_SEE_OTHER, guards=[require_admin])
async def update_cred(
    cred_id: int,
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    cred = db.get(Credential, cred_id)
    provider = CredentialProvider(data["provider"])
    cred.name = data["name"]
    cred.description = data.get("description") or None
    cred.provider = provider
    cred.ref = data.get("ref") or None
    cred.username = data.get("username") or None
    if data.get("password") or data.get("enable_password"):
        cred.encrypted_payload = _build_payload(provider, data)
    _apply_default(cred, bool(data.get("is_default")), db)
    db.commit()
    return redir("/credentials")


@post(
    "/{cred_id:int}/delete",
    dependencies={"db": provide_db},
    status_code=HTTP_303_SEE_OTHER,
    guards=[require_admin],
)
async def delete_cred(cred_id: int, db: Session) -> Redirect:
    cred = db.get(Credential, cred_id)
    if cred:
        db.delete(cred)
        db.commit()
    return redir("/credentials")


router = Router(
    path="/credentials",
    guards=[require_authenticated],
    route_handlers=[
        list_creds,
        new_cred,
        create_cred,
        bulk_creds,
        edit_cred,
        update_cred,
        delete_cred,
    ],
)
