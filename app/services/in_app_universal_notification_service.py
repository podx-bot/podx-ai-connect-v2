"""In-app conversion transport for ASKODOX app identities.

ASKODOX app users never use WhatsApp as a transport for matching, interest,
confirmation, order/deal state, or contact exchange. WhatsApp remains available
for legacy non-app flows elsewhere in the backend.
"""
from __future__ import annotations

from app.services.receipt_aware_universal_notification_service import ReceiptAwareUniversalNotificationService


class InAppUniversalNotificationService(ReceiptAwareUniversalNotificationService):
    @staticmethod
    def _is_app_user(user_id) -> bool:
        return str(user_id or "").strip().casefold().startswith("app-")

    def dispatch_plan(self, request, plan):
        """Persist app match cards as delivered in-app without calling Meta."""
        if not self._is_app_user(request.get("user_id")):
            return super().dispatch_plan(request, plan)

        request_id = int(request["id"])
        request_owner = str(request["user_id"])
        sent = skipped = 0
        results = []
        for wave in plan.get("waves") or []:
            wave_number = int(wave.get("wave") or 1)
            for target in wave.get("targets") or []:
                target_user_id = str(target.get("user_id") or "")
                if not target_user_id or not self._is_app_user(target_user_id):
                    continue
                notification_id = self.repository.reserve_notification(
                    request_id,
                    request_owner,
                    target_user_id,
                    wave_number,
                    target.get("distance_km"),
                    target.get("score"),
                )
                if notification_id is None:
                    skipped += 1
                    continue
                sent += 1
                provider_id = f"in-app:{request_id}:{target_user_id}"
                self.repository.mark_sent(notification_id, provider_id)
                results.append({
                    "target_user_id": target_user_id,
                    "result": {
                        "success": True,
                        "channel": "in_app",
                        "provider_message_id": provider_id,
                    },
                })
        return {
            "status": "IN_APP_READY" if sent else "HOLD",
            "request_id": request_id,
            "sent": sent,
            "failed": 0,
            "skipped_duplicate": skipped,
            "results": results,
            "channel": "in_app",
        }

    def register_interest(self, request, buyer_user_id, seller_user_id=None):
        if not self._is_app_user(buyer_user_id):
            return super().register_interest(request, buyer_user_id, seller_user_id)

        request_id = int(request["id"])
        if seller_user_id is None:
            responder = str(buyer_user_id)
            requester = str(request.get("user_id") or "")
            self.repository.record_interest(request_id, requester, responder)
            return {
                "status": "IN_APP_WAITING_REQUESTER_CONSENT",
                "request_id": request_id,
                "responder_user_id": responder,
                "channel": "in_app",
            }

        buyer = str(buyer_user_id)
        seller = str(seller_user_id)
        opposite = seller if str(request.get("side") or "NEED").upper() == "NEED" else buyer
        if (buyer, seller) != self.resolve_roles(request, opposite):
            return {"status": "ROLE_MISMATCH", "request_id": request_id}
        if not self._is_app_user(seller):
            return {
                "status": "APP_PARTICIPANT_REQUIRED",
                "request_id": request_id,
                "channel": "in_app",
            }
        self.repository.record_interest(request_id, buyer, seller)
        return {
            "status": "IN_APP_WAITING_SELLER_CONFIRM",
            "request_id": request_id,
            "buyer_user_id": buyer,
            "seller_user_id": seller,
            "channel": "in_app",
        }

    def confirm_lead(self, request, buyer_user_id, seller_user_id, accepted):
        if not self._is_app_user(buyer_user_id):
            return super().confirm_lead(request, buyer_user_id, seller_user_id, accepted)
        request_id = int(request["id"])
        buyer, seller = str(buyer_user_id), str(seller_user_id)
        interest = self.repository.get_interest(request_id, seller)
        if not interest or str(interest.get("requester_user_id")) != buyer:
            return {"status": "INTEREST_NOT_FOUND", "request_id": request_id}
        self.repository.set_seller_decision(request_id, seller, accepted)
        return {
            "status": "IN_APP_READY_FOR_BUYER" if accepted else "DECLINED",
            "request_id": request_id,
            "channel": "in_app",
        }

    def start_order(self, request, buyer_user_id, seller_user_id):
        if not self._is_app_user(buyer_user_id):
            return super().start_order(request, buyer_user_id, seller_user_id)
        request_id = int(request["id"])
        buyer, seller = str(buyer_user_id), str(seller_user_id)
        interest = self.repository.get_interest(request_id, seller)
        if (
            not interest
            or str(interest.get("requester_user_id")) != buyer
            or interest.get("requester_status") != "ACCEPTED"
        ):
            return {"status": "SELLER_NOT_CONFIRMED", "request_id": request_id}
        if str(request.get("side") or "").upper() == "OFFER" and request.get("price") is None:
            return {"status": "PRICE_REQUIRED", "request_id": request_id}
        self.repository.mark_waiting_address(request_id, seller)
        return {
            "status": "IN_APP_WAITING_BUYER_ADDRESS",
            "request_id": request_id,
            "channel": "in_app",
        }

    def qualify_lead(self, request, buyer_user_id, seller_user_id, delivery_address):
        if not self._is_app_user(buyer_user_id):
            return super().qualify_lead(request, buyer_user_id, seller_user_id, delivery_address)
        request_id = int(request["id"])
        buyer, seller = str(buyer_user_id), str(seller_user_id)
        address = " ".join(str(delivery_address or "").strip().split())
        if len(address) < 8:
            return {"status": "ADDRESS_TOO_SHORT", "request_id": request_id}
        interest = self.repository.get_interest(request_id, seller)
        if (
            not interest
            or str(interest.get("requester_user_id")) != buyer
            or interest.get("requester_status") != "ACCEPTED"
            or interest.get("qualification_status") != "WAITING_ADDRESS"
        ):
            return {"status": "LEAD_NOT_CONFIRMED", "request_id": request_id}
        self.repository.save_delivery_address(request_id, seller, address)
        return {
            "status": "IN_APP_WAITING_FINAL_CONFIRM",
            "request_id": request_id,
            "delivery_address": address,
            "channel": "in_app",
        }

    def final_confirm(self, request, buyer_user_id, seller_user_id, accepted=True):
        if not self._is_app_user(buyer_user_id):
            return super().final_confirm(request, buyer_user_id, seller_user_id, accepted)
        request_id = int(request["id"])
        buyer, seller = str(buyer_user_id), str(seller_user_id)
        interest = self.repository.get_interest(request_id, seller)
        if (
            not interest
            or str(interest.get("requester_user_id")) != buyer
            or interest.get("qualification_status") != "WAITING_FINAL_CONFIRM"
        ):
            return {"status": "FINAL_CONFIRM_NOT_READY", "request_id": request_id}
        if not accepted:
            self.repository.cancel_order(request_id, seller)
            return {"status": "CANCELLED", "request_id": request_id, "channel": "in_app"}
        self.repository.confirm_order(request_id, seller)
        return {"status": "CONVERTED", "request_id": request_id, "channel": "in_app"}

    def share_contacts_after_confirmation(self, request, buyer_user_id, seller_user_id):
        if not self._is_app_user(buyer_user_id):
            return super().share_contacts_after_confirmation(request, buyer_user_id, seller_user_id)
        request_id = int(request["id"])
        buyer, seller = str(buyer_user_id), str(seller_user_id)
        interest = self.repository.get_interest(request_id, seller)
        if not interest or str(interest.get("requester_user_id")) != buyer:
            return {"status": "INTEREST_NOT_FOUND", "request_id": request_id}
        if interest.get("requester_status") != "ACCEPTED":
            return {"status": "SELLER_NOT_CONFIRMED", "request_id": request_id}
        if int(interest.get("contact_shared") or 0):
            return {"status": "ALREADY_SHARED", "request_id": request_id}
        seller_contact = self.contact_resolver(seller) or {}
        buyer_contact = self.contact_resolver(buyer) or {}
        self.repository.mark_contact_shared(request_id, seller)
        return {
            "status": "CONTACT_SHARED",
            "request_id": request_id,
            "channel": "in_app",
            "buyer": {
                "name": buyer_contact.get("name") or "Buyer",
                "phone": buyer_contact.get("mobile") or buyer_contact.get("phone"),
            },
            "seller": {
                "name": seller_contact.get("business_name") or seller_contact.get("name") or "Seller",
                "phone": seller_contact.get("mobile") or seller_contact.get("phone"),
            },
        }
