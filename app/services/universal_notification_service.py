"""Role-safe Product Conversion V2 notifications.

NEED owner = buyer. OFFER owner = seller. Product cards expose known facts only;
price/stock/variant are never invented. Image media_ref is reused as a tappable
WhatsApp product image when Meta still accepts that media id.
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
        owner, opposite = str(request.get("user_id") or ""), str(opposite_user_id or "")
        side = str(request.get("side") or "").upper()
        if side == "NEED": return owner, opposite
        if side == "OFFER": return opposite, owner
        raise ValueError("Universal request side must be NEED or OFFER")

    @staticmethod
    def _money(value: Any) -> str:
        try:
            number = float(value)
            return f"₹{number:,.0f}" if number.is_integer() else f"₹{number:,.2f}"
        except (TypeError, ValueError):
            return ""

    def _send_product_image(self, mobile: str, request: Dict[str, Any], caption: str = "") -> Dict[str, Any] | None:
        media_ref = str(request.get("media_ref") or "").strip()
        sender = getattr(self.whatsapp, "send_image_by_id", None)
        if not media_ref or not callable(sender): return None
        return sender(mobile, media_ref, caption)

    def dispatch_plan(self, request: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        request_id, request_owner = int(request["id"]), str(request["user_id"])
        sent = failed = skipped = 0; results: List[Dict[str, Any]] = []
        for wave in plan.get("waves") or []:
            wave_number = int(wave.get("wave") or 1)
            for target in wave.get("targets") or []:
                target_user_id = str(target.get("user_id") or "")
                if not target_user_id: continue
                try: buyer, seller = self.resolve_roles(request, target_user_id)
                except ValueError: failed += 1; continue
                notification_id = self.repository.reserve_notification(request_id, request_owner, target_user_id, wave_number, target.get("distance_km"), target.get("score"))
                if notification_id is None: skipped += 1; continue
                buyer_contact, seller_contact = self.contact_resolver(buyer) or {}, self.contact_resolver(seller) or {}
                buyer_mobile = str(buyer_contact.get("mobile") or buyer_contact.get("phone") or buyer)
                seller_name = str(seller_contact.get("business_name") or seller_contact.get("name") or "Seller")
                self._send_product_image(buyer_mobile, request, str(request.get("subject") or "Product"))
                result = self.whatsapp.send_reply_buttons(buyer_mobile, self._buyer_match_message(request, seller_name, target), [
                    {"id": f"BUY_INTERESTED {request_id} {seller}", "title": "👍 ఆసక్తి ఉంది"},
                    {"id": f"BUY_NOT_INTERESTED {request_id} {seller}", "title": "👎 ఆసక్తి లేదు"},
                ])
                if result.get("success"): sent += 1; self.repository.mark_sent(notification_id, result.get("provider_message_id"))
                else: failed += 1; self.repository.mark_failed(notification_id)
                results.append({"target_user_id": target_user_id, "buyer_user_id": buyer, "seller_user_id": seller, "result": result})
        return {"status": "NOTIFIED" if sent else ("HOLD" if not failed else "DELIVERY_FAILED"), "request_id": request_id, "sent": sent, "failed": failed, "skipped_duplicate": skipped, "results": results}

    def register_interest(self, request: Dict[str, Any], buyer_user_id: str, seller_user_id: str) -> Dict[str, Any]:
        request_id, buyer, seller = int(request["id"]), str(buyer_user_id), str(seller_user_id)
        opposite = seller if str(request.get("side") or "").upper() == "NEED" else buyer
        if (buyer, seller) != self.resolve_roles(request, opposite): return {"status": "ROLE_MISMATCH", "request_id": request_id}
        self.repository.record_interest(request_id, buyer, seller)
        sc, bc = self.contact_resolver(seller) or {}, self.contact_resolver(buyer) or {}
        sm = str(sc.get("mobile") or sc.get("phone") or seller); buyer_name = str(bc.get("name") or "Buyer")
        self._send_product_image(sm, request, str(request.get("subject") or "Product"))
        details = self._seller_interest_message(request, buyer_name)
        delivery = self.whatsapp.send_reply_buttons(sm, details, [{"id": f"SELLER_CONFIRM {request_id} {buyer}", "title": "✅ Confirm"}, {"id": f"SELLER_DECLINE {request_id} {buyer}", "title": "❌ Decline"}])
        return {"status": "WAITING_SELLER_CONFIRM", "request_id": request_id, "buyer_user_id": buyer, "seller_user_id": seller, "notification": delivery}

    def confirm_lead(self, request: Dict[str, Any], buyer_user_id: str, seller_user_id: str, accepted: bool) -> Dict[str, Any]:
        request_id, buyer, seller = int(request["id"]), str(buyer_user_id), str(seller_user_id)
        interest = self.repository.get_interest(request_id, seller)
        if not interest or str(interest.get("requester_user_id")) != buyer: return {"status": "INTEREST_NOT_FOUND", "request_id": request_id}
        self.repository.set_seller_decision(request_id, seller, accepted)
        bc = self.contact_resolver(buyer) or {}; bm = str(bc.get("mobile") or bc.get("phone") or buyer)
        if not accepted:
            self.whatsapp.send_text_message(bm, "ఈ seller ప్రస్తుతం available కాదు. PODX మరో matchని చూపిస్తుంది.")
            return {"status": "DECLINED", "request_id": request_id}
        self._send_product_image(bm, request, str(request.get("subject") or "Product"))
        delivery = self.whatsapp.send_reply_buttons(bm, self._buyer_ready_message(request), [{"id": f"ORDER_CONTINUE {request_id} {seller}", "title": "📦 Order Continue"}, {"id": f"DIRECT_TALK {request_id} {seller}", "title": "📞 Direct Talk"}])
        return {"status": "READY_FOR_BUYER", "request_id": request_id, "buyer_user_id": buyer, "seller_user_id": seller, "notification": delivery}

    def start_order(self, request: Dict[str, Any], buyer_user_id: str, seller_user_id: str) -> Dict[str, Any]:
        request_id, buyer, seller = int(request["id"]), str(buyer_user_id), str(seller_user_id)
        interest = self.repository.get_interest(request_id, seller)
        if not interest or str(interest.get("requester_user_id")) != buyer or interest.get("requester_status") != "ACCEPTED": return {"status": "SELLER_NOT_CONFIRMED", "request_id": request_id}
        # For an OFFER, seller price is known. For a NEED-origin match this record may only contain buyer budget;
        # never mislabel buyer budget as seller price.
        if str(request.get("side") or "").upper() == "OFFER" and request.get("price") is None:
            return {"status": "PRICE_REQUIRED", "request_id": request_id}
        self.repository.mark_waiting_address(request_id, seller)
        bc = self.contact_resolver(buyer) or {}; bm = str(bc.get("mobile") or bc.get("phone") or buyer)
        delivery = self.whatsapp.send_text_message(bm, "📍 Order కోసం మీ పూర్తి delivery address పంపండి — House/Street, Area, Town, Pincode.")
        return {"status": "WAITING_BUYER_ADDRESS", "request_id": request_id, "notification": delivery}

    def qualify_lead(self, request: Dict[str, Any], buyer_user_id: str, seller_user_id: str, delivery_address: str) -> Dict[str, Any]:
        request_id, buyer, seller = int(request["id"]), str(buyer_user_id), str(seller_user_id); address = " ".join(str(delivery_address or "").strip().split())
        if len(address) < 8: return {"status": "ADDRESS_TOO_SHORT", "request_id": request_id}
        interest = self.repository.get_interest(request_id, seller)
        if not interest or str(interest.get("requester_user_id")) != buyer or interest.get("requester_status") != "ACCEPTED" or interest.get("qualification_status") != "WAITING_ADDRESS": return {"status": "LEAD_NOT_CONFIRMED", "request_id": request_id}
        self.repository.save_delivery_address(request_id, seller, address)
        sc, bc = self.contact_resolver(seller) or {}, self.contact_resolver(buyer) or {}; sm = str(sc.get("mobile") or sc.get("phone") or seller); bm = str(bc.get("mobile") or bc.get("phone") or buyer)
        self._send_product_image(sm, request, str(request.get("subject") or "Product"))
        bits = ["🛒 New Order Request", f"Product: {request.get('subject') or 'Product'}"]
        if request.get("quantity") is not None: bits.append(f"Qty: {request.get('quantity')} {request.get('unit') or ''}".strip())
        if str(request.get("side") or "").upper() == "OFFER" and request.get("price") is not None: bits.append(f"Price: {self._money(request.get('price'))}")
        bits += [f"Buyer: {bc.get('name') or 'Buyer'}", f"Delivery: {address}"]
        sd = self.whatsapp.send_text_message(sm, "\n".join(bits)); bd = self.whatsapp.send_reply_buttons(bm, "✅ Order details sellerకి పంపాను. అవసరమైతే directగా మాట్లాడవచ్చు.", [{"id": f"DIRECT_TALK {request_id} {seller}", "title": "📞 Direct Talk"}, {"id": f"DONE {request_id} {seller}", "title": "✅ Done"}])
        return {"status": "QUALIFIED_LEAD", "request_id": request_id, "buyer_user_id": buyer, "seller_user_id": seller, "seller_delivery": sd, "buyer_delivery": bd}

    def share_contacts_after_confirmation(self, request: Dict[str, Any], buyer_user_id: str, seller_user_id: str) -> Dict[str, Any]:
        request_id, buyer, seller = int(request["id"]), str(buyer_user_id), str(seller_user_id); interest = self.repository.get_interest(request_id, seller)
        if not interest or str(interest.get("requester_user_id")) != buyer: return {"status": "INTEREST_NOT_FOUND", "request_id": request_id}
        if interest.get("requester_status") != "ACCEPTED": return {"status": "SELLER_NOT_CONFIRMED", "request_id": request_id}
        if int(interest.get("contact_shared") or 0) == 1: return {"status": "ALREADY_SHARED", "request_id": request_id}
        sc, bc = self.contact_resolver(seller) or {}, self.contact_resolver(buyer) or {}; sm = str(sc.get("mobile") or sc.get("phone") or seller); bm = str(bc.get("mobile") or bc.get("phone") or buyer)
        ts = self.whatsapp.send_text_message(sm, f"PODX Buyer ✅\n{bc.get('name') or 'Buyer'}\nPhone: {bm}\nBuyer directగా మాట్లాడాలని కోరారు."); tb = self.whatsapp.send_text_message(bm, f"PODX Seller ✅\n{sc.get('business_name') or sc.get('name') or 'Seller'}\nPhone: {sm}\nఇప్పుడు directగా మాట్లాడుకోవచ్చు.")
        if ts.get("success") and tb.get("success"): self.repository.mark_contact_shared(request_id, seller); status = "CONTACT_SHARED"
        else: status = "CONTACT_SHARE_PARTIAL_FAILURE"
        return {"status": status, "request_id": request_id, "seller_delivery": ts, "buyer_delivery": tb}

    def _buyer_match_message(self, request: Dict[str, Any], seller_name: str, target: Dict[str, Any]) -> str:
        bits = ["✅ Match దొరికింది!", f"🛍️ {request.get('subject') or 'Product'}", f"Seller: {seller_name}"]
        if str(request.get("side") or "").upper() == "OFFER" and request.get("price") is not None: bits.append(f"💰 {self._money(request.get('price'))}")
        elif str(request.get("side") or "").upper() == "NEED" and request.get("price") is not None: bits.append(f"మీ budget: {self._money(request.get('price'))}")
        if request.get("quantity") is not None: bits.append(f"Qty: {request.get('quantity')} {request.get('unit') or ''}".strip())
        distance = target.get("distance_km")
        if distance is not None:
            try: bits.append(f"📍 {float(distance):.1f} km")
            except (TypeError, ValueError): pass
        bits.append("Product గురించి doubt ఉంటే PODXకి text/voiceలో అడగండి. కొనసాగాలా?")
        return "\n".join(bits)

    def _seller_interest_message(self, request: Dict[str, Any], buyer_name: str) -> str:
        bits = ["🛒 Buyer Interest", f"Product: {request.get('subject') or 'Product'}", f"Buyer: {buyer_name}"]
        if request.get("quantity") is not None: bits.append(f"Qty: {request.get('quantity')} {request.get('unit') or ''}".strip())
        if str(request.get("side") or "").upper() == "OFFER" and request.get("price") is not None: bits.append(f"Listed price: {self._money(request.get('price'))}")
        bits.append("Available అయితే Confirm చేయండి. Buyer doubts PODX ముందుగా handle చేస్తుంది.")
        return "\n".join(bits)

    def _buyer_ready_message(self, request: Dict[str, Any]) -> str:
        bits = ["✅ Seller available అని confirm చేశారు.", f"🛍️ {request.get('subject') or 'Product'}"]
        if str(request.get("side") or "").upper() == "OFFER" and request.get("price") is not None: bits.append(f"💰 Price: {self._money(request.get('price'))}")
        elif str(request.get("side") or "").upper() == "NEED": bits.append("💰 Seller final price ఇంకా listingలో లేదు — orderకు ముందు price confirm కావాలి.")
        bits.append("Product doubt ఉంటే PODXని అడగండి. కొనాలంటే Order Continue ఎంచుకోండి.")
        return "\n".join(bits)
