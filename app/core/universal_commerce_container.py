"""Container upgrade that wires the state-first universal commerce engine."""
from __future__ import annotations

from app.core.container import AppContainer
from app.repositories.receipt_aware_delivery_log_repository import ReceiptAwareDeliveryLogRepository
from app.services.end_to_end_app_flow_service import EndToEndAppFlowService
from app.services.in_app_universal_notification_service import InAppUniversalNotificationService
from app.services.reliable_universal_commerce_response_command_service import ReliableUniversalCommerceResponseCommandService
from app.services.universal_aware_conversation_service import UniversalAwareConversationService


class UniversalCommerceAppContainer(AppContainer):
    """AppContainer with universal commerce + end-to-end app routing enabled."""

    def __init__(self) -> None:
        super().__init__()

        # ASKODOX app identities use in-app conversion transport end-to-end.
        # Legacy non-app flows can still fall back to the existing WhatsApp transport
        # through the inherited receipt-aware implementation.
        self.universal_notification_service = InAppUniversalNotificationService(
            notification_repository=self.universal_notification_repository,
            whatsapp_service=self.whatsapp_service,
            contact_resolver=self._resolve_universal_contact,
        )
        self.universal_live_capture_service.notifications = self.universal_notification_service

        # Webhook delivery receipts remain attached for legacy non-app channels.
        self.delivery_log_repository = ReceiptAwareDeliveryLogRepository(
            self.database,
            delivery_status_handler=self.universal_notification_service.handle_delivery_status,
        )

        self.universal_response_command_service = ReliableUniversalCommerceResponseCommandService(
            demand_repository=self.universal_demand_repository,
            notification_service=self.universal_notification_service,
            notification_repository=self.universal_notification_repository,
        )

        universal_conversation = UniversalAwareConversationService(
            response_commands=self.universal_response_command_service,
            live_capture=self.universal_live_capture_service,
            image_service=self.universal_image_service,
            base_conversation=self.base_conversation_service,
            product_runtime=self.product_buyer_runtime_service,
            seller_escalation=self.seller_ai_escalation_service,
            grocery_runtime=self.grocery_rfq_runtime_service,
            grocery_order_runtime=self.grocery_order_runtime_service,
            catering_runtime=self.catering_rfq_runtime_service,
            catering_menu_ai=self.catering_menu_ai_service,
            event_runtime=self.event_master_runtime_service,
            event_provider_runtime=self.event_provider_runtime_service,
            ride_runtime=self.ride_runtime_service,
        )

        # One application-level entry point: profile onboarding first, then any
        # active human/deal state, and only then category-specific intelligence.
        self.conversation_service = EndToEndAppFlowService(universal_conversation)
