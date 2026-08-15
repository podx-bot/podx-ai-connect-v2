"""Role-safe Product Conversion V3 notifications with buyer final-confirm gate."""
from __future__ import annotations
from typing import Any


class UniversalNotificationService:
    def __init__(self, notification_repository, whatsapp_service, contact_resolver):
        self.repository = notification_repository
        self.whatsapp = whatsapp_service
        self.contact_resolver = contact_resolver

    @staticmethod
    def resolve_roles(request, opposite_user_id):
        owner = str(request.get("user_id") or "")
        opposite = str(opposite_user_id or "")
        side = str(request.get("side") or "").upper()
        if side == "NEED":
            return owner, opposite
        if side == "OFFER":
            return opposite, owner
        raise ValueError("Universal request side must be NEED or OFFER")

    @staticmethod
    def _money(value: Any) -> str:
        try:
            number = float(value)
            return f"₹{number:,.0f}" if number.is_integer() else f"₹{number:,.2f}"
        except (TypeError, ValueError):
            return ""

    def _send_product_image(self, mobile, request, caption=""):
        media_ref = str(request.get("media_ref") or "").strip()
        sender = getattr(self.whatsapp, "send_image_by_id", None)
        if not media_ref or not callable(sender):
            return None
        return sender(mobile, media_ref, caption)

    def dispatch_plan(self, request, plan):
        request_id = int(request["id"])
        request_owner = str(request["user_id"])
        sent = failed = skipped = 0
        results = []
        for wave in plan.get("waves") or []:
            wave_number = int(wave.get("wave") or 1)
            for target in wave.get("targets") or []:
                target_user_id = str(target.get("user_id") or "")
                if not target_user_id:
                    continue
                try:
                    buyer, seller = self.resolve_roles(request, target_user_id)
                except ValueError:
                    failed += 1
                    continue
                notification_id = self.repository.reserve_notification(
                    request_id, request_owner, target_user_id, wave_number,
                    target.get("distance_km"), target.get("score")
                )
                if notification_id is None:
                    skipped += 1
                    continue
                buyer_contact = self.contact_resolver(buyer) or {}
                seller_contact = self.contact_resolver(seller) or {}
                buyer_mobile = str(buyer_contact.get("mobile") or buyer_contact.get("phone") or buyer)
                seller_name = str(seller_contact.get("business_name") or seller_contact.get("name") or "Seller")
                self._send_product_image(buyer_mobile, request, str(request.get("subject") or "Product"))
                result = self.whatsapp.send_reply_buttons(
                    buyer_mobile,
                    self._buyer_match_message(request, seller_name, target),
                    [
                        {"id": f"BUY_INTERESTED {request_id} {seller}", "title": "👍 ఆసక్తి ఉంది"},
                        {"id": f"BUY_NOT_INTERESTED {request_id} {seller}", "title": "👎 ఆసక్తి లేదు"},
                    ],
                )
                if result.get("success"):
                    sent += 1
                    self.repository.mark_sent(notification_id, result.get("provider_message_id"))
                else:
                    failed += 1
                    self.repository.mark_failed(notification_id)
                results.append({"target_user_id": target_user_id, "buyer_user_id": buyer, "seller_user_id": seller, "result": result})
        return {
            "status": "NOTIFIED" if sent else ("HOLD" if not failed else "DELIVERY_FAILED"),
            "request_id": request_id, "sent": sent, "failed": failed,
            "skipped_duplicate": skipped, "results": results,
        }

    def register_interest(self, request, buyer_user_id, seller_user_id):
        request_id = int(request["id"])
        buyer, seller = str(buyer_user_id), str(seller_user_id)
        opposite = seller if str(request.get("side") or "").upper() == "NEED" else buyer
        if (buyer, seller) != self.resolve_roles(request, opposite):
            return {"status": "ROLE_MISMATCH", "request_id": request_id}
        self.repository.record_interest(request_id, buyer, seller)
        seller_contact = self.contact_resolver(seller) or {}
        buyer_contact = self.contact_resolver(buyer) or {}
        seller_mobile = str(seller_contact.get("mobile") or seller_contact.get("phone") or seller)
        self._send_product_image(seller_mobile, request, str(request.get("subject") or "Product"))
        result = self.whatsapp.send_reply_buttons(
            seller_mobile,
            self._seller_interest_message(request, str(buyer_contact.get("name") or "Buyer")),
            [
                {"id": f"SELLER_CONFIRM {request_id} {buyer}", "title": "✅ Confirm"},
                {"id": f"SELLER_DECLINE {request_id} {buyer}", "title": "❌ Decline"},
            ],
        )
        return {"status": "WAITING_SELLER_CONFIRM", "request_id": request_id, "notification": result}

    def confirm_lead(self, request, buyer_user_id, seller_user_id, accepted):
        request_id = int(request["id"])
        buyer, seller = str(buyer_user_id), str(seller_user_id)
        interest = self.repository.get_interest(request_id, seller)
        if not interest or str(interest.get("requester_user_id")) != buyer:
            return {"status": "INTEREST_NOT_FOUND", "request_id": request_id}
        self.repository.set_seller_decision(request_id, seller, accepted)
        buyer_contact = self.contact_resolver(buyer) or {}
        buyer_mobile = str(buyer_contact.get("mobile") or buyer_contact.get("phone") or buyer)
        if not accepted:
            self.whatsapp.send_text_message(buyer_mobile, "ఈ seller ప్రస్తుతం available కాదు. PODX మరో matchని చూపిస్తుంది.")
            return {"status": "DECLINED", "request_id": request_id}
        self._send_product_image(buyer_mobile, request, str(request.get("subject") or "Product"))
        result = self.whatsapp.send_reply_buttons(
            buyer_mobile,
            self._buyer_ready_message(request),
            [
                {"id": f"ORDER_CONTINUE {request_id} {seller}", "title": "📦 Order Continue"},
                {"id": f"DIRECT_TALK {request_id} {seller}", "title": "📞 Direct Talk"},
            ],
        )
        return {"status": "READY_FOR_BUYER", "request_id": request_id, "notification": result}

    def start_order(self, request, buyer_user_id, seller_user_id):
        request_id = int(request["id"])
        buyer, seller = str(buyer_user_id), str(seller_user_id)
        interest = self.repository.get_interest(request_id, seller)
        if not interest or str(interest.get("requester_user_id")) != buyer or interest.get("requester_status") != "ACCEPTED":
            return {"status": "SELLER_NOT_CONFIRMED", "request_id": request_id}
        if str(request.get("side") or "").upper() == "OFFER" and request.get("price") is None:
            return {"status": "PRICE_REQUIRED", "request_id": request_id}
        self.repository.mark_waiting_address(request_id, seller)
        buyer_contact = self.contact_resolver(buyer) or {}
        buyer_mobile = str(buyer_contact.get("mobile") or buyer_contact.get("phone") or buyer)
        result = self.whatsapp.send_text_message(
            buyer_mobile,
            "📍 Order కోసం మీ పూర్తి delivery address పంపండి — House/Street, Area, Town, Pincode.",
        )
        return {"status": "WAITING_BUYER_ADDRESS", "request_id": request_id, "notification": result}

    def qualify_lead(self, request, buyer_user_id, seller_user_id, delivery_address):
        request_id = int(request["id"])
        buyer, seller = str(buyer_user_id), str(seller_user_id)
        address = " ".join(str(delivery_address or "").strip().split())
        if len(address) < 8:
            return {"status": "ADDRESS_TOO_SHORT", "request_id": request_id}
        interest = self.repository.get_interest(request_id, seller)
        if (
            not interest or str(interest.get("requester_user_id")) != buyer
            or interest.get("requester_status") != "ACCEPTED"
            or interest.get("qualification_status") != "WAITING_ADDRESS"
        ):
            return {"status": "LEAD_NOT_CONFIRMED", "request_id": request_id}
        self.repository.save_delivery_address(request_id, seller, address)
        buyer_contact = self.contact_resolver(buyer) or {}
        buyer_mobile = str(buyer_contact.get("mobile") or buyer_contact.get("phone") or buyer)
        self._send_product_image(buyer_mobile, request, str(request.get("subject") or "Product"))
        bits = ["🧾 Final Order Summary", f"Product: {request.get('subject') or 'Product'}"]
        if request.get("quantity") is not None:
            bits.append(f"Qty: {request.get('quantity')} {request.get('unit') or ''}".strip())
        if str(request.get("side") or "").upper() == "OFFER" and request.get("price") is not None:
            bits.append(f"Price: {self._money(request.get('price'))}")
        bits.extend([f"Delivery: {address}", "అన్నీ సరిగా ఉంటే Confirm Order నొక్కండి."])
        result = self.whatsapp.send_reply_buttons(
            buyer_mobile,
            "\n".join(bits),
            [
                {"id": f"FINAL_CONFIRM {request_id} {seller}", "title": "✅ Confirm Order"},
                {"id": f"FINAL_CANCEL {request_id} {seller}", "title": "❌ Cancel"},
            ],
        )
        return {"status": "WAITING_FINAL_CONFIRM", "request_id": request_id, "buyer_delivery": result}

    def final_confirm(self, request, buyer_user_id, seller_user_id, accepted=True):
        request_id = int(request["id"])
        buyer, seller = str(buyer_user_id), str(seller_user_id)
        interest = self.repository.get_interest(request_id, seller)
        if not interest or str(interest.get("requester_user_id")) != buyer or interest.get("qualification_status") != "WAITING_FINAL_CONFIRM":
            return {"status": "FINAL_CONFIRM_NOT_READY", "request_id": request_id}
        if not accepted:
            self.repository.cancel_order(request_id, seller)
            return {"status": "CANCELLED", "request_id": request_id}
        self.repository.confirm_order(request_id, seller)
        seller_contact = self.contact_resolver(seller) or {}
        buyer_contact = self.contact_resolver(buyer) or {}
        seller_mobile = str(seller_contact.get("mobile") or seller_contact.get("phone") or seller)
        buyer_mobile = str(buyer_contact.get("mobile") or buyer_contact.get("phone") or buyer)
        self._send_product_image(seller_mobile, request, str(request.get("subject") or "Product"))
        bits = ["✅ New Confirmed Order", f"Product: {request.get('subject') or 'Product'}"]
        if request.get("quantity") is not None:
            bits.append(f"Qty: {request.get('quantity')} {request.get('unit') or ''}".strip())
        if str(request.get("side") or "").upper() == "OFFER" and request.get("price") is not None:
            bits.append(f"Price: {self._money(request.get('price'))}")
        bits.extend([f"Buyer: {buyer_contact.get('name') or 'Buyer'}", f"Delivery: {interest.get('delivery_address') or ''}"])
        seller_result = self.whatsapp.send_text_message(seller_mobile, "\n".join(bits))
        buyer_result = self.whatsapp.send_text_message(buyer_mobile, "✅ Order Confirmed. PODX lead converted అయింది.")
        return {"status": "CONVERTED", "request_id": request_id, "seller_delivery": seller_result, "buyer_delivery": buyer_result}

    def share_contacts_after_confirmation(self, request, buyer_user_id, seller_user_id):
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
        seller_mobile = str(seller_contact.get("mobile") or seller_contact.get("phone") or seller)
        buyer_mobile = str(buyer_contact.get("mobile") or buyer_contact.get("phone") or buyer)
        to_seller = self.whatsapp.send_text_message(seller_mobile, f"PODX Buyer ✅\n{buyer_contact.get('name') or 'Buyer'}\nPhone: {buyer_mobile}")
        to_buyer = self.whatsapp.send_text_message(buyer_mobile, f"PODX Seller ✅\n{seller_contact.get('business_name') or seller_contact.get('name') or 'Seller'}\nPhone: {seller_mobile}")
        status = "CONTACT_SHARED" if to_seller.get("success") and to_buyer.get("success") else "CONTACT_SHARE_PARTIAL_FAILURE"
        if status == "CONTACT_SHARED":
            self.repository.mark_contact_shared(request_id, seller)
        return {"status": status, "request_id": request_id}

    def _buyer_match_message(self, request, seller_name, target):
        bits = ["✅ Match దొరికింది!", f"🛍️ {request.get('subject') or 'Product'}", f"Seller: {seller_name}"]
        side = str(request.get("side") or "").upper()
        if request.get("price") is not None:
            bits.append(("💰 " if side == "OFFER" else "మీ budget: ") + self._money(request.get("price")))
        if request.get("quantity") is not None:
            bits.append(f"Qty: {request.get('quantity')} {request.get('unit') or ''}".strip())
        if target.get("distance_km") is not None:
            try:
                bits.append(f"📍 {float(target['distance_km']):.1f} km")
            except (TypeError, ValueError):
                pass
        bits.append("Product గురించి doubt ఉంటే PODXకి text/voiceలో అడగండి. కొనసాగాలా?")
        return "\n".join(bits)

    def _seller_interest_message(self, request, buyer_name):
        bits = ["🛒 Buyer Interest", f"Product: {request.get('subject') or 'Product'}", f"Buyer: {buyer_name}"]
        if request.get("quantity") is not None:
            bits.append(f"Qty: {request.get('quantity')} {request.get('unit') or ''}".strip())
        if str(request.get("side") or "").upper() == "OFFER" and request.get("price") is not None:
            bits.append(f"Listed price: {self._money(request.get('price'))}")
        bits.append("Available అయితే Confirm చేయండి. Buyer doubts PODX ముందుగా handle చేస్తుంది.")
        return "\n".join(bits)

    def _buyer_ready_message(self, request):
        bits = ["✅ Seller available అని confirm చేశారు.", f"🛍️ {request.get('subject') or 'Product'}"]
        if str(request.get("side") or "").upper() == "OFFER" and request.get("price") is not None:
            bits.append(f"💰 Price: {self._money(request.get('price'))}")
        else:
            bits.append("💰 Seller final price confirm కావాలి.")
        bits.append("Order కొనసాగించాలా, లేక directగా మాట్లాడాలా?")
        return "\n".join(bits)
