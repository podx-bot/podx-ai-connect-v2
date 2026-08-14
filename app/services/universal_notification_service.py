"""Role-safe match -> buyer interest -> seller confirm -> buyer conversion flow.

Roles come from the NEED/OFFER side, never from requester/responder position:
- NEED owner is the buyer; opposite matched user is the seller.
- OFFER owner is the seller; opposite matched user is the buyer.
"""
from __future__ import annotations
from typing import Any, Callable, Dict, List, Tuple


class UniversalNotificationService:
    def __init__(self, notification_repository, whatsapp_service, contact_resolver: Callable[[str], Dict[str, Any] | None]) -> None:
        self.repository = notification_repository
        self.whatsapp = whatsapp_service
        self.contact_resolver = contact_resolver

    @staticmethod
    def resolve_roles(request: Dict[str, Any], opposite_user_id: str) -> Tuple[str, str]:
        owner = str(request.get("user_id") or "")
        opposite = str(opposite_user_id or "")
        side = str(request.get("side") or "").upper()
        if side == "NEED":
            return owner, opposite  # buyer, seller
        if side == "OFFER":
            return opposite, owner  # buyer, seller
        raise ValueError("Universal request side must be NEED or OFFER")

    def dispatch_plan(self, request: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        """Send matched seller choices to buyers, not generic 'interest' prompts to sellers."""
        request_id = int(request["id"])
        request_owner = str(request["user_id"])
        sent = failed = skipped = 0
        results: List[Dict[str, Any]] = []
        for wave in plan.get("waves") or []:
            wave_number = int(wave.get("wave") or 1)
            for target in wave.get("targets") or []:
                target_user_id = str(target.get("user_id") or "")
                if not target_user_id:
                    continue
                try:
                    buyer_user_id, seller_user_id = self.resolve_roles(request, target_user_id)
                except ValueError:
                    failed += 1
                    continue

                notification_id = self.repository.reserve_notification(
                    request_id, request_owner, target_user_id, wave_number,
                    target.get("distance_km"), target.get("score"),
                )
                if notification_id is None:
                    skipped += 1
                    continue

                buyer = self.contact_resolver(buyer_user_id) or {}
                buyer_mobile = str(buyer.get("mobile") or buyer.get("phone") or buyer_user_id)
                seller = self.contact_resolver(seller_user_id) or {}
                seller_name = str(seller.get("name") or seller.get("business_name") or "Seller")
                result = self.whatsapp.send_reply_buttons(
                    buyer_mobile,
                    self._buyer_match_message(request, seller_name, target),
                    [
                        {"id": f"BUY_INTERESTED {request_id} {seller_user_id}", "title": "👍 ఆసక్తి ఉంది"},
                        {"id": f"BUY_NOT_INTERESTED {request_id} {seller_user_id}", "title": "👎 ఆసక్తి లేదు"},
                    ],
                )
                if result.get("success"):
                    sent += 1
                    self.repository.mark_sent(notification_id, result.get("provider_message_id"))
                else:
                    failed += 1
                    self.repository.mark_failed(notification_id)
                results.append({
                    "target_user_id": target_user_id,
                    "buyer_user_id": buyer_user_id,
                    "seller_user_id": seller_user_id,
                    "result": result,
                })
        return {
            "status": "NOTIFIED" if sent else ("HOLD" if not failed else "DELIVERY_FAILED"),
            "request_id": request_id,
            "sent": sent,
            "failed": failed,
            "skipped_duplicate": skipped,
            "results": results,
        }

    def register_interest(self, request: Dict[str, Any], buyer_user_id: str, seller_user_id: str) -> Dict[str, Any]:
        """Buyer selects a seller; only now does the seller receive Confirm/Decline."""
        request_id = int(request["id"])
        buyer = str(buyer_user_id)
        seller = str(seller_user_id)
        expected_buyer, expected_seller = self.resolve_roles(request, seller if str(request.get("side") or "").upper() == "NEED" else buyer)
        if buyer != expected_buyer or seller != expected_seller:
            return {"status": "ROLE_MISMATCH", "request_id": request_id}

        self.repository.record_interest(request_id, buyer, seller)
        seller_contact = self.contact_resolver(seller) or {}
        seller_mobile = str(seller_contact.get("mobile") or seller_contact.get("phone") or seller)
        buyer_contact = self.contact_resolver(buyer) or {}
        buyer_name = str(buyer_contact.get("name") or "Buyer")
        subject = str(request.get("subject") or "product")
        delivery = self.whatsapp.send_reply_buttons(
            seller_mobile,
            f"✅ {buyer_name} '{subject}' కొనడానికి ఆసక్తి చూపించారు. మీ దగ్గర available అయితే confirm చేయండి.",
            [
                {"id": f"SELLER_CONFIRM {request_id} {buyer}", "title": "✅ Confirm"},
                {"id": f"SELLER_DECLINE {request_id} {buyer}", "title": "❌ Decline"},
            ],
        )
        return {
            "status": "WAITING_SELLER_CONFIRM",
            "request_id": request_id,
            "buyer_user_id": buyer,
            "seller_user_id": seller,
            "notification": delivery,
        }

    def confirm_lead(self, request: Dict[str, Any], buyer_user_id: str, seller_user_id: str, accepted: bool) -> Dict[str, Any]:
        request_id = int(request["id"])
        buyer = str(buyer_user_id)
        seller = str(seller_user_id)
        interest = self.repository.get_interest(request_id, seller)
        if not interest or str(interest.get("requester_user_id")) != buyer:
            return {"status": "INTEREST_NOT_FOUND", "request_id": request_id}

        self.repository.set_seller_decision(request_id, seller, accepted)
        buyer_contact = self.contact_resolver(buyer) or {}
        buyer_mobile = str(buyer_contact.get("mobile") or buyer_contact.get("phone") or buyer)
        subject = str(request.get("subject") or "product")
        if not accepted:
            self.whatsapp.send_text_message(
                buyer_mobile,
                "ఈ seller ప్రస్తుతం available కాదు. PODX మరో matchని చూపిస్తుంది.",
            )
            return {"status": "DECLINED", "request_id": request_id, "buyer_user_id": buyer, "seller_user_id": seller}

        delivery = self.whatsapp.send_reply_buttons(
            buyer_mobile,
            f"✅ Seller '{subject}' కోసం confirm చేశారు. ఇప్పుడు ఎలా కొనసాగాలి?",
            [
                {"id": f"ORDER_CONTINUE {request_id} {seller}", "title": "📦 Order Continue"},
                {"id": f"DIRECT_TALK {request_id} {seller}", "title": "📞 Direct Talk"},
            ],
        )
        return {
            "status": "READY_FOR_BUYER",
            "request_id": request_id,
            "buyer_user_id": buyer,
            "seller_user_id": seller,
            "notification": delivery,
        }

    def start_order(self, request: Dict[str, Any], buyer_user_id: str, seller_user_id: str) -> Dict[str, Any]:
        request_id = int(request["id"])
        buyer = str(buyer_user_id)
        seller = str(seller_user_id)
        interest = self.repository.get_interest(request_id, seller)
        if not interest or str(interest.get("requester_user_id")) != buyer or interest.get("requester_status") != "ACCEPTED":
            return {"status": "SELLER_NOT_CONFIRMED", "request_id": request_id}
        self.repository.mark_waiting_address(request_id, seller)
        buyer_contact = self.contact_resolver(buyer) or {}
        buyer_mobile = str(buyer_contact.get("mobile") or buyer_contact.get("phone") or buyer)
        delivery = self.whatsapp.send_text_message(
            buyer_mobile,
            "📍 Delivery కోసం మీ పూర్తి address పంపండి — House/Street, Area, Town, Pincode. Saved address ఉంటే తర్వాత reuse చేయవచ్చు.",
        )
        return {"status": "WAITING_BUYER_ADDRESS", "request_id": request_id, "notification": delivery}

    def qualify_lead(self, request: Dict[str, Any], buyer_user_id: str, seller_user_id: str, delivery_address: str) -> Dict[str, Any]:
        request_id = int(request["id"])
        buyer = str(buyer_user_id)
        seller = str(seller_user_id)
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
        seller_contact = self.contact_resolver(seller) or {}
        buyer_contact = self.contact_resolver(buyer) or {}
        seller_mobile = str(seller_contact.get("mobile") or seller_contact.get("phone") or seller)
        buyer_mobile = str(buyer_contact.get("mobile") or buyer_contact.get("phone") or buyer)
        buyer_name = str(buyer_contact.get("name") or "Buyer")
        subject = str(request.get("subject") or "Product")
        price = request.get("price")
        quantity = request.get("quantity")
        unit = request.get("unit") or ""

        bits = ["✅ Qualified Order Lead", f"Product: {subject}"]
        if quantity is not None:
            bits.append(f"Qty: {quantity} {unit}".strip())
        if price is not None and str(request.get("side") or "").upper() == "OFFER":
            bits.append(f"Price: ₹{price}")
        bits.extend([f"Buyer: {buyer_name}", f"Delivery: {address}"])
        seller_delivery = self.whatsapp.send_text_message(seller_mobile, "\n".join(bits))
        buyer_delivery = self.whatsapp.send_reply_buttons(
            buyer_mobile,
            "✅ మీ delivery details sellerకి పంపాను. అవసరమైతే sellerతో directగా మాట్లాడవచ్చు.",
            [
                {"id": f"DIRECT_TALK {request_id} {seller}", "title": "📞 Direct Talk"},
                {"id": f"DONE {request_id} {seller}", "title": "✅ Done"},
            ],
        )
        return {
            "status": "QUALIFIED_LEAD",
            "request_id": request_id,
            "buyer_user_id": buyer,
            "seller_user_id": seller,
            "seller_delivery": seller_delivery,
            "buyer_delivery": buyer_delivery,
        }

    def share_contacts_after_confirmation(self, request: Dict[str, Any], buyer_user_id: str, seller_user_id: str) -> Dict[str, Any]:
        """Direct Talk is allowed after the seller has confirmed; address is not required."""
        request_id = int(request["id"])
        buyer = str(buyer_user_id)
        seller = str(seller_user_id)
        interest = self.repository.get_interest(request_id, seller)
        if not interest or str(interest.get("requester_user_id")) != buyer:
            return {"status": "INTEREST_NOT_FOUND", "request_id": request_id}
        if interest.get("requester_status") != "ACCEPTED":
            return {"status": "SELLER_NOT_CONFIRMED", "request_id": request_id}
        if int(interest.get("contact_shared") or 0) == 1:
            return {"status": "ALREADY_SHARED", "request_id": request_id}

        seller_contact = self.contact_resolver(seller) or {}
        buyer_contact = self.contact_resolver(buyer) or {}
        seller_mobile = str(seller_contact.get("mobile") or seller_contact.get("phone") or seller)
        buyer_mobile = str(buyer_contact.get("mobile") or buyer_contact.get("phone") or buyer)
        seller_name = str(seller_contact.get("name") or "Seller")
        buyer_name = str(buyer_contact.get("name") or "Buyer")
        to_seller = self.whatsapp.send_text_message(
            seller_mobile,
            f"PODX Buyer ✅\n{buyer_name}\nPhone: {buyer_mobile}\nBuyer directగా మాట్లాడాలని కోరారు.",
        )
        to_buyer = self.whatsapp.send_text_message(
            buyer_mobile,
            f"PODX Seller ✅\n{seller_name}\nPhone: {seller_mobile}\nఇప్పుడు directగా మాట్లాడుకోవచ్చు.",
        )
        if to_seller.get("success") and to_buyer.get("success"):
            self.repository.mark_contact_shared(request_id, seller)
            status = "CONTACT_SHARED"
        else:
            status = "CONTACT_SHARE_PARTIAL_FAILURE"
        return {
            "status": status,
            "request_id": request_id,
            "buyer_user_id": buyer,
            "seller_user_id": seller,
            "seller_delivery": to_seller,
            "buyer_delivery": to_buyer,
        }

    @staticmethod
    def _buyer_match_message(request: Dict[str, Any], seller_name: str, target: Dict[str, Any]) -> str:
        subject = str(request.get("subject") or "product")
        bits = ["✅ Match దొరికింది!", f"Product: {subject}", f"Seller: {seller_name}"]
        if str(request.get("side") or "").upper() == "OFFER" and request.get("price") is not None:
            bits.append(f"Price: ₹{request.get('price')}")
        distance = target.get("distance_km")
        if distance is not None:
            try:
                bits.append(f"Distance: {float(distance):.1f} km")
            except (TypeError, ValueError):
                pass
        bits.append("ఈ sellerతో కొనసాగాలా?")
        return "\n".join(bits)
