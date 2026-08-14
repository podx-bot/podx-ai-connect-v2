"""Target → Interest → Seller confirm → Buyer qualification → optional contact exchange."""
from __future__ import annotations
from typing import Any, Callable, Dict, List


class UniversalNotificationService:
    def __init__(self, notification_repository, whatsapp_service, contact_resolver: Callable[[str], Dict[str, Any] | None]) -> None:
        self.repository = notification_repository
        self.whatsapp = whatsapp_service
        self.contact_resolver = contact_resolver

    def dispatch_plan(self, request: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        request_id = int(request["id"])
        requester = str(request["user_id"])
        sent = failed = skipped = 0
        results: List[Dict[str, Any]] = []
        for wave in plan.get("waves") or []:
            wave_number = int(wave.get("wave") or 1)
            for target in wave.get("targets") or []:
                target_user_id = str(target.get("user_id") or "")
                if not target_user_id:
                    continue
                notification_id = self.repository.reserve_notification(
                    request_id, requester, target_user_id, wave_number,
                    target.get("distance_km"), target.get("score"),
                )
                if notification_id is None:
                    skipped += 1
                    continue
                contact = self.contact_resolver(target_user_id) or {}
                mobile = str(contact.get("mobile") or contact.get("phone") or target_user_id)
                result = self.whatsapp.send_reply_buttons(
                    mobile,
                    self._target_message(request),
                    [
                        {"id": f"INTERESTED {request_id}", "title": "👍 ఆసక్తి ఉంది"},
                        {"id": f"NOT_INTERESTED {request_id}", "title": "👎 ఆసక్తి లేదు"},
                    ],
                )
                if result.get("success"):
                    sent += 1
                    self.repository.mark_sent(notification_id, result.get("provider_message_id"))
                else:
                    failed += 1
                    self.repository.mark_failed(notification_id)
                results.append({"target_user_id": target_user_id, "result": result})
        return {
            "status": "NOTIFIED" if sent else ("HOLD" if not failed else "DELIVERY_FAILED"),
            "request_id": request_id,
            "sent": sent,
            "failed": failed,
            "skipped_duplicate": skipped,
            "results": results,
        }

    def register_interest(self, request: Dict[str, Any], responder_user_id: str) -> Dict[str, Any]:
        request_id = int(request["id"])
        requester = str(request["user_id"])
        responder = str(responder_user_id)
        self.repository.record_interest(request_id, requester, responder)
        contact = self.contact_resolver(requester) or {}
        mobile = str(contact.get("mobile") or contact.get("phone") or requester)
        subject = str(request.get("subject") or "requirement")
        delivery = self.whatsapp.send_reply_buttons(
            mobile,
            f"✅ '{subject}' కోసం ఒక buyer ఆసక్తి చూపించారు. ఈ leadని కొనసాగించాలా?",
            [
                {"id": f"CONFIRM {request_id}", "title": "✅ Confirm"},
                {"id": f"NO {request_id}", "title": "❌ Decline"},
            ],
        )
        return {
            "status": "WAITING_REQUESTER_CONSENT",
            "request_id": request_id,
            "responder_user_id": responder,
            "notification": delivery,
        }

    def confirm_lead(self, request: Dict[str, Any], responder_user_id: str, accepted: bool) -> Dict[str, Any]:
        """Seller/requester decides once. Accepted leads move to buyer qualification, not contact exchange."""
        request_id = int(request["id"])
        requester = str(request["user_id"])
        responder = str(responder_user_id)
        self.repository.set_requester_consent(request_id, responder, accepted)
        if not accepted:
            responder_contact = self.contact_resolver(responder) or {}
            responder_mobile = str(responder_contact.get("mobile") or responder_contact.get("phone") or responder)
            self.whatsapp.send_text_message(
                responder_mobile,
                "ఈ seller ప్రస్తుతం ఈ leadని continue చేయలేకపోతున్నారు. PODX మరో match కోసం చూస్తుంది.",
            )
            return {"status": "DECLINED", "request_id": request_id, "responder_user_id": responder}

        interest = self.repository.get_interest(request_id, responder)
        if not interest or interest.get("responder_status") != "INTERESTED":
            return {"status": "INTEREST_NOT_FOUND", "request_id": request_id}

        buyer_contact = self.contact_resolver(responder) or {}
        buyer_mobile = str(buyer_contact.get("mobile") or buyer_contact.get("phone") or responder)
        subject = str(request.get("subject") or "product")
        prompt = (
            f"✅ Seller ready — '{subject}' lead continue అవుతోంది.\n"
            "Delivery కోసం మీ పూర్తి address పంపండి. ఉదా: House/Street, Area, Town, Pincode."
        )
        delivery = self.whatsapp.send_text_message(buyer_mobile, prompt)
        return {
            "status": "WAITING_BUYER_ADDRESS",
            "request_id": request_id,
            "responder_user_id": responder,
            "notification": delivery,
        }

    def qualify_lead(self, request: Dict[str, Any], responder_user_id: str, delivery_address: str) -> Dict[str, Any]:
        """Capture buyer address, send one final qualified-lead card to seller, and keep contact optional."""
        request_id = int(request["id"])
        requester = str(request["user_id"])
        responder = str(responder_user_id)
        address = " ".join(str(delivery_address or "").strip().split())
        if len(address) < 8:
            return {"status": "ADDRESS_TOO_SHORT", "request_id": request_id}

        interest = self.repository.get_interest(request_id, responder)
        if not interest or interest.get("requester_status") != "ACCEPTED":
            return {"status": "LEAD_NOT_CONFIRMED", "request_id": request_id}

        self.repository.save_delivery_address(request_id, responder, address)
        seller = self.contact_resolver(requester) or {}
        buyer = self.contact_resolver(responder) or {}
        seller_mobile = str(seller.get("mobile") or seller.get("phone") or requester)
        buyer_mobile = str(buyer.get("mobile") or buyer.get("phone") or responder)
        buyer_name = str(buyer.get("name") or "Buyer")
        subject = str(request.get("subject") or "Product")
        price = request.get("price")
        quantity = request.get("quantity")
        unit = request.get("unit") or ""

        bits = ["✅ Qualified Lead", f"Product: {subject}"]
        if quantity is not None:
            bits.append(f"Qty: {quantity} {unit}".strip())
        if price is not None:
            bits.append(f"Price: ₹{price}")
        bits.extend([f"Buyer: {buyer_name}", f"Delivery: {address}"])
        seller_delivery = self.whatsapp.send_text_message(seller_mobile, "\n".join(bits))

        buyer_delivery = self.whatsapp.send_reply_buttons(
            buyer_mobile,
            "✅ మీ delivery details sellerకి పంపాను. అవసరమైతే మాత్రమే sellerతో directగా మాట్లాడండి.",
            [
                {"id": f"CONTACT {request_id}", "title": "📞 Sellerతో మాట్లాడాలి"},
                {"id": f"DONE {request_id}", "title": "✅ Done"},
            ],
        )
        return {
            "status": "QUALIFIED_LEAD",
            "request_id": request_id,
            "responder_user_id": responder,
            "seller_delivery": seller_delivery,
            "buyer_delivery": buyer_delivery,
        }

    def share_contacts_after_confirmation(self, request: Dict[str, Any], responder_user_id: str) -> Dict[str, Any]:
        """Buyer may request direct contact after seller already confirmed; seller is not asked again."""
        request_id = int(request["id"])
        requester = str(request["user_id"])
        responder = str(responder_user_id)
        interest = self.repository.get_interest(request_id, responder)
        if not interest or interest.get("requester_status") != "ACCEPTED":
            return {"status": "SELLER_NOT_CONFIRMED", "request_id": request_id}
        if str(interest.get("qualification_status") or "") != "QUALIFIED":
            return {"status": "LEAD_NOT_QUALIFIED", "request_id": request_id}
        if int(interest.get("contact_shared") or 0) == 1:
            return {"status": "ALREADY_SHARED", "request_id": request_id}

        a = self.contact_resolver(requester) or {}
        b = self.contact_resolver(responder) or {}
        a_mobile = str(a.get("mobile") or a.get("phone") or requester)
        b_mobile = str(b.get("mobile") or b.get("phone") or responder)
        a_name = str(a.get("name") or "Seller")
        b_name = str(b.get("name") or "Buyer")
        to_a = self.whatsapp.send_text_message(
            a_mobile,
            f"PODX Lead ✅\n{b_name}\nPhone: {b_mobile}\nBuyer direct contact కోరారు.",
        )
        to_b = self.whatsapp.send_text_message(
            b_mobile,
            f"PODX Seller ✅\n{a_name}\nPhone: {a_mobile}\nఇప్పుడు directగా మాట్లాడుకోవచ్చు.",
        )
        if to_a.get("success") and to_b.get("success"):
            self.repository.mark_contact_shared(request_id, responder)
            status = "CONTACT_SHARED"
        else:
            status = "CONTACT_SHARE_PARTIAL_FAILURE"
        return {
            "status": status,
            "request_id": request_id,
            "responder_user_id": responder,
            "requester_delivery": to_a,
            "responder_delivery": to_b,
        }

    @staticmethod
    def _target_message(request: Dict[str, Any]) -> str:
        subject = str(request.get("subject") or "requirement")
        quantity = request.get("quantity")
        unit = request.get("unit") or ""
        price = request.get("price")
        bits = [f"✅ Match దొరికింది!\n{subject}"]
        if quantity is not None:
            bits.append(f"Qty: {quantity} {unit}".strip())
        if price is not None:
            bits.append(f"₹{price}")
        bits.append("మీకు ఆసక్తి ఉందా?")
        return "\n".join(bits)
