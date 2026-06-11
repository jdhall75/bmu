"""Auth routes: login, OIDC callback, logout, and dev fake-login."""

from __future__ import annotations

from authlib.integrations.httpx_client import AsyncOAuth2Client
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry
from joserfc import jwt as jose_jwt
from litestar import Router, get, post
from litestar.connection import Request
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER

from kiroku.config import get_settings
from kiroku.logging import get_logger
from kiroku.web.redir import redir

log = get_logger(__name__)


def _redirect_uri() -> str:
    return f"{get_settings().base_url.rstrip('/')}/auth/callback"


def _extract_roles(claims: dict, claim_path: str) -> list[str]:
    """Walk a dot-path through JWT claims to reach a roles list."""
    node: object = claims
    for key in claim_path.split("."):
        if not isinstance(node, dict):
            return []
        node = node.get(key, {})
    return node if isinstance(node, list) else []


# ---------------------------------------------------------------------------
# /auth/login
# ---------------------------------------------------------------------------

@get("/login", exclude_from_auth=True)
async def login(request: Request) -> Redirect | Template:
    s = get_settings()
    if s.auth_provider == "none":
        return redir("/")
    if s.auth_provider == "dev":
        return redir("/auth/dev-login")

    try:
        async with AsyncOAuth2Client(
            client_id=s.oidc_client_id,
            redirect_uri=_redirect_uri(),
            scope="openid profile email",
            timeout=10,
        ) as client:
            resp = await client.get(f"{s.oidc_issuer_url}/.well-known/openid-configuration")
            resp.raise_for_status()
            oidc = resp.json()
            url, state = client.create_authorization_url(oidc["authorization_endpoint"])
    except Exception as exc:
        log.error("oidc discovery failed", error=str(exc))
        return Template("auth/error.html", context={"error": f"OIDC discovery failed: {exc}"})

    request.session["oidc_state"] = state
    request.session["oidc_token_endpoint"] = oidc["token_endpoint"]
    request.session["oidc_jwks_uri"] = oidc["jwks_uri"]
    return Redirect(url)


# ---------------------------------------------------------------------------
# /auth/callback  (OIDC only)
# ---------------------------------------------------------------------------

@get("/callback", exclude_from_auth=True)
async def callback(request: Request, code: str = "", error: str = "") -> Redirect | Template:
    if error:
        return Template("auth/error.html", context={"error": f"Keycloak error: {error}"})

    oauth_state = request.query_params.get("state", "")
    expected_state = request.session.get("oidc_state")
    if not oauth_state or oauth_state != expected_state:
        return Template("auth/error.html", context={"error": "Invalid state parameter — possible CSRF."})

    s = get_settings()
    token_endpoint = request.session.get("oidc_token_endpoint", "")
    jwks_uri = request.session.get("oidc_jwks_uri", "")

    try:
        async with AsyncOAuth2Client(
            client_id=s.oidc_client_id,
            client_secret=s.oidc_client_secret,
            redirect_uri=_redirect_uri(),
            timeout=15,
        ) as client:
            tokens = await client.fetch_token(
                token_endpoint,
                grant_type="authorization_code",
                code=code,
            )
            jwks_resp = await client.get(jwks_uri)
            jwks_resp.raise_for_status()
            jwks = jwks_resp.json()
    except Exception as exc:
        log.error("oidc token exchange failed", error=str(exc))
        return Template("auth/error.html", context={"error": f"Token exchange failed: {exc}"})

    try:
        key_set = KeySet.import_key_set(jwks)
        token = jose_jwt.decode(tokens["id_token"], key_set)
        JWTClaimsRegistry().validate(token.claims)
    except Exception as exc:
        log.error("oidc jwt validation failed", error=str(exc))
        return Template("auth/error.html", context={"error": f"JWT validation failed: {exc}"})

    claims = token.claims
    roles = _extract_roles(claims, s.oidc_role_claim)
    if s.oidc_admin_role in roles:
        role = "admin"
    elif s.oidc_operator_role in roles:
        role = "operator"
    else:
        log.warning("oidc login denied: no matching role", sub=claims.get("sub"), roles=roles)
        return Template(
            "auth/error.html",
            context={"error": "Your account has no Kiroku role assigned. Contact your administrator."},
        )

    request.session["user_sub"] = claims.get("sub", "")
    request.session["user_name"] = claims.get("name") or claims.get("preferred_username", "")
    request.session["user_email"] = claims.get("email", "")
    request.session["user_role"] = role
    for k in ("oidc_state", "oidc_token_endpoint", "oidc_jwks_uri"):
        request.session.pop(k, None)

    log.info("user logged in", sub=claims.get("sub"), role=role)
    return redir("/")


# ---------------------------------------------------------------------------
# /auth/logout
# ---------------------------------------------------------------------------

@post("/logout", status_code=HTTP_303_SEE_OTHER, exclude_from_auth=True)
async def logout(request: Request) -> Redirect:
    request.session.clear()
    return redir("/auth/login")


# ---------------------------------------------------------------------------
# /auth/dev-login  (dev mode only)
# ---------------------------------------------------------------------------

@get("/dev-login", exclude_from_auth=True)
async def dev_login_form(request: Request) -> Template | Redirect:
    if get_settings().auth_provider != "dev":
        return redir("/")
    return Template("auth/dev_login.html", context={})


@post("/dev-login", status_code=HTTP_303_SEE_OTHER, exclude_from_auth=True)
async def dev_login_submit(
    request: Request,
    data: dict = Body(media_type=RequestEncodingType.URL_ENCODED),
) -> Redirect | Template:
    if get_settings().auth_provider != "dev":
        return redir("/")
    role = data.get("role", "operator")
    if role not in ("admin", "operator"):
        role = "operator"
    request.session["user_sub"] = f"dev-{role}"
    request.session["user_name"] = f"Dev {role.capitalize()}"
    request.session["user_email"] = f"{role}@dev.local"
    request.session["user_role"] = role
    return redir("/")


router = Router(
    path="/auth",
    route_handlers=[login, callback, logout, dev_login_form, dev_login_submit],
)
