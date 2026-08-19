"""Delivery log repository that forwards WhatsApp receipts to recovery hooks."""
from __future__ import annotations

from app.repositories.delivery_log_repository import DeliveryLogRepository


class ReceiptAwareDeliveryLogRepository(DeliveryLogRepository):
    def __init__(self, database, delivery_status_handler=None) -> None:
        super().__init__(database)
        self.delivery_status_handler = delivery_status_handler

    def save_status(self, provider_message_id, recipient_mobile, status, error_message):
        super().save_status(provider_message_id, recipient_mobile, status, error_message)
        handler = self.delivery_status_handler
        if callable(handler):
            try:
                handler(
                    provider_message_id=str(provider_message_id or ""),
                    status=str(status or ""),
                    error_message=error_message,
                )
            except Exception:
                # Delivery logging must never fail because a recovery hook failed.
                pass
