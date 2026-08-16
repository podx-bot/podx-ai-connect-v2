"""WhatsApp runtime for local delivery partner opt-in, offers, first-accept and delivery status."""
from __future__ import annotations

import math
import re
from typing import Optional


class LocalDispatchRuntimeService:
    def __init__(self, dispatch_repository, user_repository, whatsapp_service, contact_resolver) -> None:
        self.dispatch = dispatch_repository
        self.users = user_repository
        self.whatsapp = whatsapp_service
        self.contact_resolver = contact_resolver

    def process(self, sender_user_id: str, message: str) -> Optional[str]:
        clean = " ".join(str(message or "").strip().split())
        lowered = clean.casefold()
        if lowered in {"delivery on", "delivery partner", "delivery partner on", "dpartner on"}:
            return self._enable_partner(sender_user_id)
        patterns = (
            (r"^(?:dtake|delivery accept)\s+#?(\d+)$", self._claim),
            (r"^(?:dpickup|delivery pickup)\s+#?(\d+)$", self._picked_up),
            (r"^(?:donway|delivery onway|delivery on the way)\s+#?(\d+)$", self._on_the_way),
            (r"^(?:ddelivered|delivery delivered)\s+#?(\d+)$", self._delivered),
        )
        for pattern, handler in patterns:
            match = re.match(pattern, clean, re.I)
            if match:
                return handler(sender_user_id, int(match.group(1)))
        return None

    def offer_task(self, task_id: int, limit: int = 12, radius_km: float = 15.0) -> dict:
        task = self.dispatch.get(task_id)
        if not task or str(task.get("status")) != "OPEN":
            return {"offered": 0, "status": "NOT_OPEN"}
        partners = self._find_delivery_partners()
        pickup_lat = task.get("pickup_lat")
        pickup_lon = task.get("pickup_lon")
        ranked = []
        for partner in partners:
            partner_id = str(partner.get("whatsapp_mobile") or "")
            if not partner_id or partner_id in {str(task.get("buyer_user_id")), str(task.get("seller_user_id"))}:
                continue
            distance = self._distance_km(pickup_lat, pickup_lon, partner.get("latitude"), partner.get("longitude"))
            if distance is not None and distance > radius_km:
                continue
            ranked.append((distance if distance is not None else 9999.0, partner_id, partner))
        ranked.sort(key=lambda item: item[0])
        offered = 0
        for distance_sort, partner_id, partner in ranked[:limit]:
            distance = None if distance_sort >= 9999 else distance_sort
            self.dispatch.offer(task_id, partner_id, distance)
            mobile = str(partner.get("whatsapp_mobile") or partner_id)
            fee = task.get("fee")
            fee_text = f"\nDelivery fee: ₹{float(fee):.0f}" if fee is not None else ""
            distance_text = f"\nPickup distance: {distance:.1f} km" if distance is not None else ""
            body = (
                f"🚚 PODX Delivery Task #{task_id}\n"
                f"Pickup: {task.get('pickup_text') or 'Seller location'}\n"
                f"Drop: {task.get('drop_text') or 'Buyer address'}"
                f"{distance_text}{fee_text}\n"
                f"Accept చేయాలంటే DTAKE {task_id}"
            )
            self.whatsapp.send_reply_buttons(mobile, body, [{"id": f"DTAKE {task_id}", "title": "🚚 Accept"}])
            offered += 1
        return {"offered": offered, "status": "OFFERED" if offered else "NO_PARTNERS"}

    def _find_delivery_partners(self) -> list[dict]:
        rows = self.users.database.fetchall(
            """
            SELECT u.*
            FROM users u
            JOIN user_capabilities c ON c.whatsapp_mobile = u.whatsapp_mobile
            WHERE u.registration_complete = 1
              AND c.capability = 'DELIVERY_PARTNER'
              AND u.latitude IS NOT NULL
              AND u.longitude IS NOT NULL
            ORDER BY u.updated_at DESC
            """
        )
        return [dict(row) for row in rows]

    def _enable_partner(self, user_id: str) -> str:
        user = self.users.find_by_whatsapp_mobile(str(user_id)) or {}
        if int(user.get("registration_complete") or 0) != 1:
            return "Delivery Partnerగా join అవ్వడానికి ముందుగా PODX registration complete చేయండి."
        self.users.add_capability(str(user_id), "DELIVERY_PARTNER", source="delivery_runtime")
        if user.get("latitude") is None or user.get("longitude") is None:
            return "✅ Delivery Partner mode ON. Nearby tasks పొందడానికి ఒకసారి Current Location share చేయండి."
        return "✅ Delivery Partner mode ON. మీ దగ్గరలో delivery task వస్తే PODX notify చేస్తుంది."

    def _claim(self, user_id: str, task_id: int) -> str:
        if not self.users.has_capability(str(user_id), "DELIVERY_PARTNER"):
            return "ముందుగా DELIVERY ON అని పంపి Delivery Partner mode enable చేయండి."
        if not self.dispatch.claim(task_id, str(user_id)):
            task = self.dispatch.get(task_id) or {}
            if task.get("assigned_partner_id"):
                return f"Delivery Task #{task_id} ఇప్పటికే మరో partner accept చేశారు."
            return f"Delivery Task #{task_id} మీకు availableగా లేదు."
        task = self.dispatch.get(task_id) or {}
        self._notify_assignment(task, str(user_id))
        return f"✅ Delivery Task #{task_id} మీకు assign అయింది. Pickup అయిన తర్వాత DPICKUP {task_id} పంపండి."

    def _picked_up(self, user_id: str, task_id: int) -> str:
        return self._status(user_id, task_id, "PICKED_UP", f"✅ Pickup saved. Next: DONWAY {task_id}")

    def _on_the_way(self, user_id: str, task_id: int) -> str:
        return self._status(user_id, task_id, "ON_THE_WAY", f"🚚 On the way saved. Delivered తర్వాత DDELIVERED {task_id}")

    def _delivered(self, user_id: str, task_id: int) -> str:
        result = self._status(user_id, task_id, "DELIVERED", f"✅ Delivery Task #{task_id} completed.")
        if result.startswith("✅"):
            task = self.dispatch.get(task_id) or {}
            buyer = self.contact_resolver(str(task.get("buyer_user_id") or "")) or {}
            seller = self.contact_resolver(str(task.get("seller_user_id") or "")) or {}
            self.whatsapp.send_text_message(str(buyer.get("mobile") or task.get("buyer_user_id")), f"✅ మీ Order delivery complete అయింది. Task #{task_id}.")
            self.whatsapp.send_text_message(str(seller.get("mobile") or task.get("seller_user_id")), f"✅ Order delivery complete అయింది. Task #{task_id}.")
        return result

    def _status(self, user_id: str, task_id: int, status: str, success_reply: str) -> str:
        if self.dispatch.update_status(task_id, str(user_id), status):
            return success_reply
        return f"Delivery Task #{task_id} status update చేయలేకపోయాను. Assignment/status check చేయండి."

    def _notify_assignment(self, task: dict, partner_id: str) -> None:
        buyer = self.contact_resolver(str(task.get("buyer_user_id") or "")) or {}
        seller = self.contact_resolver(str(task.get("seller_user_id") or "")) or {}
        partner = self.contact_resolver(partner_id) or {}
        partner_name = str(partner.get("name") or "Delivery Partner")
        msg = f"🚚 Delivery Partner assigned: {partner_name}. Task #{task.get('id')}."
        self.whatsapp.send_text_message(str(buyer.get("mobile") or task.get("buyer_user_id")), msg)
        self.whatsapp.send_text_message(str(seller.get("mobile") or task.get("seller_user_id")), msg)

    @staticmethod
    def _distance_km(lat1, lon1, lat2, lon2):
        if None in {lat1, lon1, lat2, lon2}:
            return None
        try:
            p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
            dlat = p2 - p1
            dlon = math.radians(float(lon2) - float(lon1))
            a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
            return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        except (TypeError, ValueError):
            return None
