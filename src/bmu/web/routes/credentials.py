from litestar import Router, get, post
from litestar.params import Body
from litestar.enums import RequestEncodingType
from litestar.response import Redirect, Template
from sqlalchemy import select
from sqlalchemy.orm import Session

from bmu.credentials.local import LocalCredentialResolver
from bmu.models import Credential, CredentialProvider
from bmu.web.deps import provide_db


@get("/", dependencies={"db": provide_db})
async def list_creds(db: Session) -> Template:
    creds = db.scalars(select(Credential).order_by(Credential.name)).all()
    return Template(template_name="credentials/list.html", context={"credentials": creds})


@get("/new")
async def new_cred() -> Template:
    return Template(
        template_name="credentials/form.html",
        context={"providers": [p.value for p in CredentialProvider]},
    )


@post("/", dependencies={"db": provide_db})
async def create_cred(
    db: Session,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect:
    provider = CredentialProvider(data["provider"])
    payload = None
    if provider is CredentialProvider.LOCAL:
        local = LocalCredentialResolver()
        secret = {
            "username": data.get("username"),
            "password": data.get("password") or None,
            "enable_password": data.get("enable_password") or None,
        }
        payload = local.encrypt({k: v for k, v in secret.items() if v is not None})

    cred = Credential(
        name=data["name"],
        description=data.get("description") or None,
        provider=provider,
        encrypted_payload=payload,
        ref=data.get("ref") or None,
        username=data.get("username") or None,
    )
    db.add(cred)
    db.commit()
    return Redirect(path="/credentials")


router = Router(path="/credentials", route_handlers=[list_creds, new_cred, create_cred])
