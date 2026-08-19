"""Delivery-hardened Universal Notification Service.

Adds a plain-text fallback for seller interest notifications and reports a
hard failure when both interactive and text delivery fail.
"""
from __future__ import annotations

from app.services.universal_notification_service import UniversalNotificationService


class ReliableUniversalNotificationService(UniversalNotificationService):
    def register_interest(self, request, buyer_user_id, seller_user_id=None):
        result = super().register_interest(request, buyer_user_id, seller_user_id)
        if seller_user_id is None:
            return result
        if result.get("status") != "WAITING_SELLER_CONFIRM":
            return result

        delivery = dict(result.get("notification") or {})
        if delivery.get("success"):
            return result

        buyer = str(buyer_user_id)
        seller = str(seller_user_id)
        request_id = int(request["id"])
        seller_contact = self.contact_resolver(seller) or {}
        buyer_contact = self.contact_resolver(buyer) or {}
        seller_mobile = str(seller_contact.get("mobile") or seller_contact.get("phone") or seller)
        body = self._seller_interest_message(request, str(buyer_contact.get("name") or "Buyer"))
        fallback = self.whatsapp.send_text_message(
            seller_mobile,
            body + "\n\nButtons delivery కాలేదు. Confirm అయితే CONFIRM అని, వద్దంటే DECLINE అని reply చేయండి.",
        )
        return {
            **result,
            "status": "WAITING_SELLER_CONFIRM" if fallback.get("success") else "SELLER_NOTIFICATION_FAILED",
            "request_id": request_id,
            "notification": fallback,
            "interactive_delivery": delivery,
            "fallback_used": True,
        }
