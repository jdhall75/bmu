from kiroku.web.routes.api import devices

from litestar import Router

from kiroku.web.auth import require_admin

router = Router(path="/api/v1", guards=[require_admin], route_handlers=[devices.router])
