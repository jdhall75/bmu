from kiroku.web.routes.api import devices

from litestar import Router

router = Router(path="/api/v1", route_handlers=[devices.router])
