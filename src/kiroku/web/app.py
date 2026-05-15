import hashlib
import time
from pathlib import Path

from litestar import Litestar, Request
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.exceptions import NotAuthorizedException
from litestar.middleware import DefineMiddleware
from litestar.response import Redirect, Response
from litestar.static_files import create_static_files_router
from litestar.template.config import TemplateConfig

from kiroku.config import get_settings
from kiroku.logging import configure_logging
from kiroku.web.auth import KirokuAuthMiddleware, _request_ctx, current_user
from kiroku.web.routes import (
    compliance,
    credentials,
    cve,
    dashboard,
    devices,
    docs,
    groups,
    jobs,
    parsers,
    platforms,
    runs,
    schedules,
    search,
)
from kiroku.web.routes.api import router as api_router
from kiroku.web.routes.auth import router as auth_router

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


async def _stamp_start(request: Request) -> None:
    request.state.start_time = time.perf_counter()
    _request_ctx.set(request)


def _configure_jinja(engine: JinjaTemplateEngine) -> None:
    def elapsed_ms(request: Request) -> float | None:
        start = getattr(request.state, "start_time", None)
        if start is None:
            return None
        return round((time.perf_counter() - start) * 1000, 1)

    engine.engine.globals["elapsed_ms"] = elapsed_ms
    engine.engine.globals["current_user"] = current_user


def _auth_exception_handler(request: Request, exc: NotAuthorizedException) -> Response:
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return Redirect("/auth/login")
    return Response(content={"detail": "Unauthorized"}, status_code=401, media_type="application/json")


def _build_middleware(settings) -> list:
    if settings.auth_provider == "none":
        return []
    from litestar.middleware.session.client_side import CookieBackendConfig

    secret = hashlib.sha256(settings.secret_key.encode()).digest()[:32]
    session_config = CookieBackendConfig(
        secret=secret,
        key="kiroku_session",
        max_age=28800,  # 8 hours
        samesite="lax",
        secure=False,
    )
    return [
        session_config.middleware,
        DefineMiddleware(KirokuAuthMiddleware, exclude=["^/static"]),
    ]


def create_app() -> Litestar:
    configure_logging()
    settings = get_settings()
    return Litestar(
        route_handlers=[
            api_router,
            auth_router,
            dashboard.router,
            docs.router,
            groups.router,
            devices.router,
            platforms.router,
            jobs.router,
            parsers.router,
            credentials.router,
            schedules.router,
            runs.router,
            cve.router,
            search.router,
            compliance.router,
            create_static_files_router(path="/static", directories=[STATIC_DIR]),
        ],
        middleware=_build_middleware(settings),
        before_request=_stamp_start,
        template_config=TemplateConfig(
            directory=TEMPLATES_DIR,
            engine=JinjaTemplateEngine,
            engine_callback=_configure_jinja,
        ),
        exception_handlers={NotAuthorizedException: _auth_exception_handler},
        debug=False,
    )


app = create_app()
