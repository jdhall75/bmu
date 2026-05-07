from pathlib import Path

from litestar import Litestar
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.static_files import create_static_files_router
from litestar.template.config import TemplateConfig

from kiroku.logging import configure_logging
from kiroku.web.routes import (
    credentials,
    cve,
    dashboard,
    devices,
    groups,
    platforms,
    profiles,
    runs,
    schedules,
    search,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> Litestar:
    configure_logging()
    return Litestar(
        route_handlers=[
            dashboard.router,
            groups.router,
            devices.router,
            platforms.router,
            profiles.router,
            credentials.router,
            schedules.router,
            runs.router,
            cve.router,
            search.router,
            create_static_files_router(path="/static", directories=[STATIC_DIR]),
        ],
        template_config=TemplateConfig(
            directory=TEMPLATES_DIR, engine=JinjaTemplateEngine
        ),
        debug=False,
    )


app = create_app()
