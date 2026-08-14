"""Target → Notify → Interest → Consent → Contact orchestration for Universal Flow V1."""

from __future__ import annotations

from typing import Any, Callable, Dict, List


class UniversalNotificationService:
    def __init__(
        self,
        notification_repository,
        whatsapp_service,
        contact_resolver: Callable[[str], Dict[str, Any] | None],
    ) -> None:
        self.repository = notification_repository
        self.whatsapp = whatsapp_service
        self.contact_resolver = contact_resolver

    def dispatch_plan(self, request: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        request_id = int(request["id"])
        requester = str(request["user_id"])
        sent = 0
        failed = 0
        skipped = 0
        results: List[Dict[str, Any]] = []

        for wave in plan.get("waves") or []:
            wave_number = int(wave.get("wave") or 1)
            for target in wave.get("targets") or []:
                target_user_id = str(target.get("user_id") or "")
                if not target_user_id:
                    continue
                notification_id = self.repository.reserve_notification(
                    request_id=request_id,
                    requester_user_id=requester,
                    target_user_id=target_user_id,
                    wave=wave_number,
                    distance_km=target.get("distance_km"),
                    relevance_score=target.get("score"),
                )
                if notification_id is None:
                    skipped += 1
                    continue

                contact = self.contact_resolver(target_user_id) or {}
                mobile = str(contact.get("mobile") or contact.get("phone") or target_user_id)
                message = self._target_message(request, request_id)
                result = self.whatsapp.send_text_message(mobile, message)
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

        requester_contact = self.contact_resolver(requester) or {}
        mobile = str(requester_contact.get("mobile") or requester_contact.get("phone") or requester)
        subject = str(request.get("subject") or "requirement")
        prompt = (
            f"PODX: మీ '{subject}' requirement కి ఒకరు interested అన్నారు. "
            f"Contact share చేయాలంటే CONFIRM {request_id} అని reply చేయండి. "
            "వద్దంటే NO అని reply చేయండి."
        )
        delivery = self.whatsapp.send_text_message(mobile, prompt)
        return {
            "status": "WAITING_REQUESTER_CONSENT",
            "request_id": request_id,
            "responder_user_id": responder,
            "notification": delivery,
        }

    def confirm_and_share_contacts(
        self,
        request: Dict[str, Any],
        responder_user_id: str,
        accepted: bool,
    ) -> Dict[str, Any]:
        request_id = int(request["id"])
        requester = str(request["user_id"])
        responder = str(responder_user_id)
        self.repository.set_requester_consent(request_id, responder, accepted)
        if not accepted:
            return {"status": "DECLINED", "request_id": request_id, "responder_user_id": responder}

        interest = self.repository.get_interest(request_id, responder)
        if not interest or interest.get("responder_status") != "INTERESTED":
            return {"status": "INTEREST_NOT_FOUND", "request_id": request_id}
        if int(interest.get("contact_shared") or 0) == 1:
            return {"status": "ALREADY_SHARED", "request_id": request_id}

        a = self.contact_resolver(requester) or {}
        b = self.contact_resolver(responder) or {}
        a_mobile = str(a.get("mobile") or a.get("phone") or requester)
        b_mobile = str(b.get("mobile") or b.get("phone") or responder)
        a_name = str(a.get("name") or "Party A")
        b_name = str(b.get("name") or "Party B")

        to_a = self.whatsapp.send_text_message(
            a_mobile,
            f"PODX Match ✅\n{b_name}\nPhone: {b_mobile}\nమీరు directగా మాట్లాడుకోవచ్చు.",
        )
        to_b = self.whatsapp.send_text_message(
            b_mobile,
            f"PODX Match ✅\n{a_name}\nPhone: {a_mobile}\nమీరు directగా మాట్లాడుకోవచ్చు.",
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
    def _target_message(request: Dict[str, Any], request_id: int) -> str:
        subject = str(request.get("subject") or "requirement")
        quantity = request.get("quantity")
        unit = request.get("unit") or ""
        price = request.get("price")
        bits = [f"PODX nearby request: {subject}"]
        if quantity is not None:
            bits.append(f"Qty: {quantity} {unit}".strip())
        if price is not None:
            bits.append(f"Budget/Price: ₹{price}")
        bits.append(f"మీరు fulfil చేయగలిగితే INTERESTED {request_id} అని reply చేయండి.")
        return "\n".join(bits)
