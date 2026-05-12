import time
from pathlib import Path

from litestar import Litestar, Request
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.static_files import create_static_files_router
from litestar.template.config import TemplateConfig

from kiroku.logging import configure_logging
from kiroku.web.routes import (
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

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def _stamp_start(request: Request) -> None:
    request.state.start_time = time.perf_counter()


def _configure_jinja(engine: JinjaTemplateEngine) -> None:
    def elapsed_ms(request: Request) -> float | None:
        start = getattr(request.state, "start_time", None)
        if start is None:
            return None
        return round((time.perf_counter() - start) * 1000, 1)

    engine.engine.globals["elapsed_ms"] = elapsed_ms


def create_app() -> Litestar:
    configure_logging()
    return Litestar(
        route_handlers=[
            api_router,
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
            create_static_files_router(path="/static", directories=[STATIC_DIR]),
        ],
        before_request=_stamp_start,
        template_config=TemplateConfig(
            directory=TEMPLATES_DIR,
            engine=JinjaTemplateEngine,
            engine_callback=_configure_jinja,
        ),
        debug=False,
    )


app = create_app()
