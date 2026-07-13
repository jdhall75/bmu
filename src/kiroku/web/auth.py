"""Authentication middleware, guards, and user model for Kiroku.

Three modes (KIROKU_AUTH_PROVIDER):
  none  – no auth enforced; all routes open (default, for trusted networks)
  dev   – fake login form; choose operator or admin locally
  oidc  – full Keycloak OIDC / OAuth2 code flow (production)
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException
from litestar.handlers import BaseRouteHandler
from litestar.middleware.authentication import AbstractAuthenticationMiddleware, AuthenticationResult

from kiroku.config import get_settings

# Populated by the before_request hook so current_user() works in Jinja2 globals.
_request_ctx: ContextVar[ASGIConnection | None] = ContextVar("_request_ctx", default=None)


@dataclass
class User:
    sub: str
    username: str
    email: str
    role: str  # "admin" | "operator"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_operator(self) -> bool:
        return self.role in ("admin", "operator")


class KirokuAuthMiddleware(AbstractAuthenticationMiddleware):
    """Reads the session populated by cookie session middleware and sets request.user."""

    async def authenticate_request(self, connection: ASGIConnection) -> AuthenticationResult:
        session = connection.scope.get("session") or {}
        sub = session.get("user_sub")
        if not sub:
            return AuthenticationResult(user=None, auth=None)
        role = session.get("user_role", "operator")
        if role not in ("admin", "operator"):
            role = "operator"
        user = User(
            sub=sub,
            username=session.get("user_name", ""),
            email=session.get("user_email", ""),
            role=role,
        )
        return AuthenticationResult(user=user, auth=user)


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def require_authenticated(connection: ASGIConnection, handler: BaseRouteHandler) -> None:
    """Allow any logged-in user. No-op when auth_provider=none."""
    if get_settings().auth_provider == "none":
        return
    if not connection.user:
        raise NotAuthorizedException()


def require_admin(connection: ASGIConnection, handler: BaseRouteHandler) -> None:
    """Allow admin role only. No-op when auth_provider=none."""
    if get_settings().auth_provider == "none":
        return
    user = connection.user
    if not user or not user.is_admin:
        raise NotAuthorizedException()


# ---------------------------------------------------------------------------
# Jinja2 global
# ---------------------------------------------------------------------------

def current_user() -> User | None:
    """Return the authenticated User for the current request, or None."""
    connection = _request_ctx.get(None)
    if connection is None:
        return None
    return connection.scope.get("user")
