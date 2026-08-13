from fastapi import FastAPI

from app.api.appointment_location_middleware import AppointmentLocationMiddleware
from app.api.routes.debug import router as debug_router
from app.api.routes.fast_webhook import router as webhook_router
from app.api.routes.health import router as health_router
from app.core.container import AppContainer


def create_app() -> FastAPI:
    app = FastAPI(
        title="PODX AI CONNECT V2",
        version="2.0.0"
    )

    container = AppContainer()
    app.state.container = container
    app.add_middleware(AppointmentLocationMiddleware, container=container)

    app.include_router(health_router)
    app.include_router(webhook_router)
    app.include_router(debug_router)

    @app.on_event("shutdown")
    def shutdown_event() -> None:
        container.close()

    return app
