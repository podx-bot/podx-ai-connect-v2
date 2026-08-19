"""Receipt-aware seller interest delivery with async WhatsApp failure recovery."""
from __future__ import annotations

import re

from app.repositories.seller_interest_delivery_repository import SellerInterestDeliveryRepository
from app.services.reliable_universal_notification_service import ReliableUniversalNotificationService
from app.services.seller_utility_template_service import SellerUtilityTemplateService


class ReceiptAwareUniversalNotificationService(ReliableUniversalNotificationService):
    REENGAGEMENT_META_CODE = "131047"

    def __init__(self, notification_repository, whatsapp_service, contact_resolver):
        super().__init__(notification_repository, whatsapp_service, contact_resolver)
        db_path = str(getattr(notification_repository, "db_path", "podx.db") or "podx.db")
        self.seller_delivery_receipts = SellerInterestDeliveryRepository(db_path)
        self.seller_template = SellerUtilityTemplateService(whatsapp_service)

    def _fallback_body(self, request, buyer_name: str) -> str:
        body = self._seller_interest_message(request, buyer_name)
        return body + "\n\nButtons delivery కాలేదు. Confirm అయితే CONFIRM అని, వద్దంటే DECLINE అని reply చేయండి."

    @staticmethod
    def _meta_error_code(error_message: str | None) -> str:
        match = re.search(r"(?:META_CODE=|['\"]code['\"]\s*:\s*)(\d+)", str(error_message or ""))
        return match.group(1) if match else ""

    def register_interest(self, request, buyer_user_id, seller_user_id=None):
        result = super().register_interest(request, buyer_user_id, seller_user_id)
        if seller_user_id is None:
            return result
        if str(result.get("status") or "") != "WAITING_SELLER_CONFIRM":
            return result

        delivery = dict(result.get("notification") or {})
        provider_message_id = str(delivery.get("provider_message_id") or "").strip()
        if not provider_message_id:
            return result

        buyer = str(buyer_user_id)
        seller = str(seller_user_id)
        seller_contact = self.contact_resolver(seller) or {}
        buyer_contact = self.contact_resolver(buyer) or {}
        seller_mobile = str(seller_contact.get("mobile") or seller_contact.get("phone") or seller)
        buyer_mobile = str(buyer_contact.get("mobile") or buyer_contact.get("phone") or buyer)
        buyer_name = str(buyer_contact.get("name") or "Buyer")
        self.seller_delivery_receipts.record(
            request_id=int(request["id"]),
            buyer_user_id=buyer,
            seller_user_id=seller,
            seller_mobile=seller_mobile,
            buyer_mobile=buyer_mobile,
            fallback_body=self._fallback_body(request, buyer_name),
            provider_message_id=provider_message_id,
            channel="text_fallback" if result.get("fallback_used") else "interactive",
            retry_count=1 if result.get("fallback_used") else 0,
        )
        return result

    def _record_template_delivery(self, receipt: dict, result: dict) -> dict:
        provider_id = str(result.get("provider_message_id") or "").strip()
        if result.get("success") and provider_id:
            self.seller_delivery_receipts.record(
                request_id=receipt["request_id"],
                buyer_user_id=receipt["buyer_user_id"],
                seller_user_id=receipt["seller_user_id"],
                seller_mobile=receipt["seller_mobile"],
                buyer_mobile=receipt.get("buyer_mobile") or "",
                fallback_body=receipt["fallback_body"],
                provider_message_id=provider_id,
                channel="utility_template",
                retry_count=1,
            )
            return {"status": "UTILITY_TEMPLATE_SENT", "notification": result}
        return {
            "status": "UTILITY_TEMPLATE_FAILED",
            "notification": result,
        }

    def handle_delivery_status(self, provider_message_id: str, status: str, error_message: str | None = None):
        receipt = self.seller_delivery_receipts.by_provider_message_id(provider_message_id)
        if receipt is None:
            return None

        normalized = str(status or "").strip().lower()
        self.seller_delivery_receipts.mark_status(receipt["id"], normalized or "unknown", error_message)
        if normalized not in {"failed", "undelivered"}:
            return {"status": "TRACKED", "delivery_status": normalized}

        meta_code = self._meta_error_code(error_message)
        channel = str(receipt.get("channel") or "")

        # Meta 131047 means a free-form re-engagement send is outside the allowed
        # customer-service window. Retrying another free-form message cannot fix
        # that condition; use an approved Utility template instead.
        if meta_code == self.REENGAGEMENT_META_CODE and channel != "utility_template":
            template = self.seller_template.send_seller_interest(
                recipient_mobile=receipt["seller_mobile"],
                summary=receipt["fallback_body"],
                request_id=receipt["request_id"],
            )
            template_result = self._record_template_delivery(receipt, template)
            if template_result["status"] == "UTILITY_TEMPLATE_SENT":
                return {
                    **template_result,
                    "meta_error_code": meta_code,
                }
            if template.get("status") == "SELLER_UTILITY_TEMPLATE_NOT_CONFIGURED":
                return {
                    "status": "UTILITY_TEMPLATE_REQUIRED",
                    "meta_error_code": meta_code,
                    "required_env": template.get("required_env"),
                }

        if channel == "interactive" and int(receipt.get("retry_count") or 0) < 1 and meta_code != self.REENGAGEMENT_META_CODE:
            fallback = self.whatsapp.send_text_message(receipt["seller_mobile"], receipt["fallback_body"])
            fallback_id = str(fallback.get("provider_message_id") or "").strip()
            if fallback.get("success") and fallback_id:
                self.seller_delivery_receipts.record(
                    request_id=receipt["request_id"],
                    buyer_user_id=receipt["buyer_user_id"],
                    seller_user_id=receipt["seller_user_id"],
                    seller_mobile=receipt["seller_mobile"],
                    buyer_mobile=receipt.get("buyer_mobile") or "",
                    fallback_body=receipt["fallback_body"],
                    provider_message_id=fallback_id,
                    channel="text_fallback",
                    retry_count=1,
                )
                return {"status": "FALLBACK_SENT", "notification": fallback}

        buyer_mobile = str(receipt.get("buyer_mobile") or "").strip()
        buyer_notice = None
        diagnostic = f" Meta code: {meta_code}." if meta_code else ""
        if buyer_mobile:
            buyer_notice = self.whatsapp.send_text_message(
                buyer_mobile,
                "⚠️ Seller WhatsApp delivery పూర్తికాలేదు. మీ interest save అయింది; PODX ఈ sellerని unavailable deliveryగా mark చేసి next match ప్రయత్నించాలి." + diagnostic,
            )
        return {
            "status": "FINAL_DELIVERY_FAILED",
            "buyer_notice": buyer_notice,
            "meta_error_code": meta_code or None,
            "error_message": error_message,
        }
