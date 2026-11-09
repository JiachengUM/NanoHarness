from fastapi import FastAPI

from projects.nanoai.api import router as session_router
from projects.nanoai.service import SessionService


def create_app(*, session_service: SessionService | None = None) -> FastAPI:
    app = FastAPI(title="NanoAI", version="0.1.0")
    app.state.session_service = session_service or SessionService()
    app.include_router(session_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Minimal HTTP demo endpoint."""

        return {"status": "ok"}

    return app


app = create_app()
