from starlette.routing import Mount

from aicore.v2.experiments.v2_frontend_duplex_backend import (
    app as v2_agent_duplex_app,
)
from projects.mind.test_backend.main import app


def test_v2_agent_duplex_app_is_mounted_under_api_prefix() -> None:
    route = next(
        route
        for route in app.routes
        if isinstance(route, Mount) and route.path == "/api/v2-agent"
    )

    assert route.app is v2_agent_duplex_app
