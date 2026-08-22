from fastapi import FastAPI

from app.api.appointment_location_middleware import AppointmentLocationMiddleware
from app.api.routes.debug import router as debug_router
from app.api.routes.fast_webhook import router as webhook_router
from app.api.routes.health import router as health_router
from app.api.routes.in_app_deal import router as in_app_deal_router
from app.core.universal_commerce_container import UniversalCommerceAppContainer
from app.repositories.conversation_observability_repository import ConversationObservabilityRepository
from app.repositories.conversation_turn_ledger_repository import ConversationTurnLedgerRepository
from app.repositories.driver_kyc_repository import DriverKYCRepository
from app.repositories.podx_meet_repository import PodxMeetRepository
from app.services.admin_monitoring_runtime_service import AdminMonitoringRuntimeService
from app.services.admin_monitoring_service import AdminMonitoringService
from app.services.conversation_os_runtime_service import ConversationOSRuntimeService
from app.services.customer_facing_response_policy import CustomerFacingResponsePolicy
from app.services.domain_complaint_prevention_service import DomainComplaintPreventionService
from app.services.driver_kyc_runtime_service import DriverKYCAwareConversationService, DriverKYCRuntimeService
from app.services.dynamic_role_profile_attachment_service import DynamicRoleProfileAttachmentService
from app.services.end_to_end_app_flow_service import EndToEndAppFlowService
from app.services.fresh_test_reset_service import FreshTestResetService
from app.services.multilingual_onboarding_service import MultilingualOnboardingService
from app.services.natural_conversation_orchestrator import NaturalConversationOrchestrator
from app.services.podx_meet_aware_conversation_service import PodxMeetAwareConversationService
from app.services.podx_meet_runtime_service import PodxMeetRuntimeService
from app.services.progressive_role_profile_essentials_service import ProgressiveRoleProfileEssentialsService
from app.services.ride_settlement_runtime_service import RideSettlementRuntimeService
from app.services.runtime_complaint_prevention_service import RuntimeComplaintPreventionService
from app.services.universal_category_flow_brain import UniversalCategoryFlowBrain
from app.services.universal_correction_service import UniversalCorrectionService
from app.services.universal_profile_summary_service import UniversalProfileSummaryService


def create_app() -> FastAPI:
    app = FastAPI(title="PODX AI CONNECT V2", version="2.0.0")

    container = UniversalCommerceAppContainer()
    meet_repository = PodxMeetRepository(container.settings.database_path)
    meet_runtime = PodxMeetRuntimeService(meet_repository, user_repository=container.user_repository)
    container.podx_meet_repository = meet_repository
    container.podx_meet_runtime_service = meet_runtime
    container.conversation_service = PodxMeetAwareConversationService(meet_runtime=meet_runtime, delegate=container.conversation_service)

    kyc_repository = DriverKYCRepository(container.settings.database_path)
    kyc_runtime = DriverKYCRuntimeService(kyc_repository, user_repository=container.user_repository)
    container.driver_kyc_repository = kyc_repository
    container.driver_kyc_runtime_service = kyc_runtime
    container.conversation_service = DriverKYCAwareConversationService(kyc_runtime=kyc_runtime, delegate=container.conversation_service)

    settlement_runtime = RideSettlementRuntimeService(
        delegate=container.conversation_service,
        ride_repository=container.ride_repository,
        whatsapp_service=container.whatsapp_service,
        user_repository=container.user_repository,
    )
    container.ride_settlement_runtime_service = settlement_runtime
    container.ride_settlement_repository = settlement_runtime.settlements
    container.conversation_service = settlement_runtime

    observability_repository = ConversationObservabilityRepository(container.settings.database_path)
    category_brain = UniversalCategoryFlowBrain()
    orchestrator = NaturalConversationOrchestrator(
        delegate=container.conversation_service,
        observability_repository=observability_repository,
        category_brain=category_brain,
        handlers={
            "RIDE": settlement_runtime,
            "KYC": kyc_runtime,
            "MEET": meet_runtime,
            "EVENT": container.event_master_runtime_service,
            "APPOINTMENT": container.appointment_service,
            "PRODUCT": container.product_buyer_runtime_service,
            "SERVICE": container.base_conversation_service,
            "JOB": container.base_conversation_service,
            "LEDGER": getattr(container.conversation_service, "ledger_runtime", None),
        },
    )
    session_registry = getattr(container.base_conversation_service, "session_registry", None)
    profile_essentials = ProgressiveRoleProfileEssentialsService(container.user_repository)
    role_attachment = DynamicRoleProfileAttachmentService(
        delegate=orchestrator,
        category_brain=category_brain,
        user_repository=container.user_repository,
        profile_essentials=profile_essentials,
        session_registry=session_registry,
    )
    profile_summary = UniversalProfileSummaryService(
        delegate=role_attachment,
        user_repository=container.user_repository,
        marketplace_repository=container.marketplace_repository,
    )
    container.universal_category_flow_brain = category_brain
    container.conversation_observability_repository = observability_repository
    container.natural_conversation_orchestrator = orchestrator
    container.progressive_role_profile_essentials_service = profile_essentials
    container.dynamic_role_profile_attachment_service = role_attachment
    container.universal_profile_summary_service = profile_summary

    monitoring = AdminMonitoringService(container.settings.database_path)
    admin_runtime = AdminMonitoringRuntimeService(monitoring=monitoring, delegate=profile_summary)
    container.admin_monitoring_service = monitoring
    container.admin_monitoring_runtime_service = admin_runtime

    onboarding = MultilingualOnboardingService(
        delegate=container.base_conversation_service,
        session_registry=session_registry,
    )
    container.multilingual_onboarding_service = onboarding

    app_flow = EndToEndAppFlowService(
        inner_service=admin_runtime,
        base_conversation=onboarding,
        response_commands=container.universal_response_command_service,
    )
    container.end_to_end_app_flow_service = app_flow

    fresh_test = FreshTestResetService(
        delegate=app_flow,
        user_repository=container.user_repository,
        session_registry=session_registry,
    )
    container.fresh_test_reset_service = fresh_test

    correction = UniversalCorrectionService(
        delegate=fresh_test,
        user_repository=container.user_repository,
        session_registry=session_registry,
    )
    container.universal_correction_service = correction

    domain_guard = DomainComplaintPreventionService(
        delegate=correction,
        category_brain=category_brain,
        observability_repository=observability_repository,
    )
    container.domain_complaint_prevention_service = domain_guard

    quality_guard = RuntimeComplaintPreventionService(
        delegate=domain_guard,
        category_brain=category_brain,
        observability_repository=observability_repository,
    )
    container.runtime_complaint_prevention_service = quality_guard

    # Conversation OS stays on the synchronous WhatsApp hot path, so it must not
    # add a second blocking model call before the existing runtime can answer.
    # It builds continuity from the durable turn ledger and raw prior turn; deeper
    # semantic enrichment belongs off the reply-critical path.
    conversation_os_ledger = ConversationTurnLedgerRepository(container.settings.database_path)
    conversation_os = ConversationOSRuntimeService(
        delegate=quality_guard,
        ledger_repository=conversation_os_ledger,
        request_extractor=None,
        channel="whatsapp",
    )
    container.conversation_turn_ledger_repository = conversation_os_ledger
    container.conversation_os_runtime_service = conversation_os

    # Outermost response boundary: every domain may reason with internal state,
    # but no channel should expose implementation vocabulary to a customer.
    customer_response_policy = CustomerFacingResponsePolicy(
        delegate=conversation_os,
        ledger_repository=conversation_os_ledger,
    )
    container.customer_facing_response_policy = customer_response_policy
    container.conversation_service = customer_response_policy

    app.state.container = container
    app.add_middleware(AppointmentLocationMiddleware, container=container)
    app.include_router(health_router)
    app.include_router(webhook_router)
    app.include_router(debug_router)
    app.include_router(in_app_deal_router)

    @app.on_event("shutdown")
    def shutdown_event() -> None:
        container.close()

    return app
