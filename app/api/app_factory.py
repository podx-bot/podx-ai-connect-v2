from fastapi import FastAPI

from app.api.appointment_location_middleware import AppointmentLocationMiddleware
from app.api.routes.debug import router as debug_router
from app.api.routes.fast_webhook import router as webhook_router
from app.api.routes.health import router as health_router
from app.core.container import AppContainer
from app.repositories.driver_kyc_repository import DriverKYCRepository
from app.repositories.podx_meet_repository import PodxMeetRepository
from app.services.driver_kyc_runtime_service import DriverKYCAwareConversationService, DriverKYCRuntimeService
from app.services.podx_meet_aware_conversation_service import PodxMeetAwareConversationService
from app.services.podx_meet_runtime_service import PodxMeetRuntimeService
from app.services.ride_settlement_runtime_service import RideSettlementRuntimeService


def create_app() -> FastAPI:
    app = FastAPI(
        title="PODX AI CONNECT V2",
        version="2.0.0"
    )

    container = AppContainer()
    meet_repository = PodxMeetRepository(container.settings.database_path)
    meet_runtime = PodxMeetRuntimeService(meet_repository, user_repository=container.user_repository)
    container.podx_meet_repository = meet_repository
    container.podx_meet_runtime_service = meet_runtime
    container.conversation_service = PodxMeetAwareConversationService(
        meet_runtime=meet_runtime,
        delegate=container.conversation_service,
    )

    kyc_repository = DriverKYCRepository(container.settings.database_path)
    kyc_runtime = DriverKYCRuntimeService(kyc_repository, user_repository=container.user_repository)
    container.driver_kyc_repository = kyc_repository
    container.driver_kyc_runtime_service = kyc_runtime
    container.conversation_service = DriverKYCAwareConversationService(
        kyc_runtime=kyc_runtime,
        delegate=container.conversation_service,
    )

    settlement_runtime = RideSettlementRuntimeService(
        delegate=container.conversation_service,
        ride_repository=container.ride_repository,
        whatsapp_service=container.whatsapp_service,
        user_repository=container.user_repository,
    )
    container.ride_settlement_runtime_service = settlement_runtime
    container.ride_settlement_repository = settlement_runtime.settlements
    container.conversation_service = settlement_runtime

    app.state.container = container
    app.add_middleware(AppointmentLocationMiddleware, container=container)

    app.include_router(health_router)
    app.include_router(webhook_router)
    app.include_router(debug_router)

    @app.on_event("shutdown")
    def shutdown_event() -> None:
        container.close()

    return app
