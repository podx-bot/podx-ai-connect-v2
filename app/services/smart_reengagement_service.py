"""Target prior local product NEEDs when a matching seller product becomes available."""
from __future__ import annotations

import hashlib
import math
from typing import Any, Dict


class SmartReengagementService:
    def __init__(self, demand_repository, catalog_repository, user_repository,
                 reengagement_repository, whatsapp_service, radius_km: float = 25.0,
                 alert_preferences=None) -> None:
        self.demands = demand_repository
        self.catalog = catalog_repository
        self.users = user_repository
        self.ledger = reengagement_repository
        self.whatsapp = whatsapp_service
        self.radius_km = max(1.0, float(radius_km))
        self.alert_preferences = alert_preferences or self._auto_alert_preferences(catalog_repository)

    @staticmethod
    def _auto_alert_preferences(repository):
        try:
            db_path = str(getattr(repository, "db_path", "") or "")
            if not db_path:
                return None
            from app.repositories.proactive_alert_preference_repository import ProactiveAlertPreferenceRepository
            return ProactiveAlertPreferenceRepository(db_path)
        except Exception:
            return None

    def notify_product_available(self, seller_user_id: str, product_id: int) -> Dict[str, Any]:
        product = self.catalog.get(int(product_id))
        if not product or not int(product.get("active") or 0):
            return {"status": "PRODUCT_NOT_ACTIVE", "sent": 0}
        if str(product.get("stock_status") or "UNKNOWN").upper() == "OUT_OF_STOCK":
            return {"status": "OUT_OF_STOCK", "sent": 0}

        seller = self.users.find_by_whatsapp_mobile(str(seller_user_id)) or {}
        seller_lat = seller.get("latitude")
        seller_lon = seller.get("longitude")
        fingerprint = self._fingerprint(product)
        sent = 0
        matches = []

        for need in self.demands.list_active(limit=1000):
            if str(need.get("side") or "").upper() != "NEED":
                continue
            if str(need.get("domain") or "").upper() != "PRODUCT":
                continue
            buyer_id = str(need.get("user_id") or "")
            if not buyer_id or buyer_id == str(seller_user_id):
                continue
            if self.alert_preferences is not None and not self.alert_preferences.is_enabled(buyer_id):
                continue
            if self._similarity(need.get("subject"), product.get("subject")) < 0.72:
                continue

            distance = None
            if seller_lat is not None and seller_lon is not None and need.get("latitude") is not None and need.get("longitude") is not None:
                distance = self._distance_km(float(seller_lat), float(seller_lon), float(need["latitude"]), float(need["longitude"]))
                if distance > self.radius_km:
                    continue
            elif not self._same_area(need.get("location_text"), seller.get("location_name") or seller.get("area")):
                continue

            if not self.ledger.claim(
                buyer_user_id=buyer_id,
                seller_user_id=str(seller_user_id),
                demand_id=int(need["id"]),
                product_id=int(product["id"]),
                fingerprint=fingerprint,
            ):
                continue

            buyer = self.users.find_by_whatsapp_mobile(buyer_id) or {}
            mobile = str(buyer.get("whatsapp_mobile") or buyer_id)
            result = self._send_alert(mobile, need, product, seller, str(seller_user_id), distance)
            if bool(result.get("success")):
                sent += 1
                matches.append({"buyer_user_id": buyer_id, "demand_id": int(need["id"]), "distance_km": distance})
            else:
                self.ledger.release(buyer_id, int(product["id"]), fingerprint)

        return {"status": "NOTIFIED" if sent else "NO_NEW_MATCH", "sent": sent, "matches": matches}

    def _send_alert(self, mobile: str, need: Dict[str, Any], product: Dict[str, Any],
                    seller: Dict[str, Any], seller_user_id: str, distance: float | None):
        seller_name = str(seller.get("business_name") or seller.get("name") or "Nearby seller")
        bits = [
            "🔔 PODX Smart Alert",
            f"మీరు ముందు వెతికిన '{need.get('subject')}' ఇప్పుడు దగ్గరలో available ఉంది.",
            f"Seller: {seller_name}",
        ]
        if product.get("price") is not None:
            bits.append(f"Price: ₹{self._money(product.get('price'))}")
        if distance is not None:
            bits.append(f"Distance: {distance:.1f} km")
        bits.append("ఇంకా కావాలంటే Interested నొక్కండి.")
        body = "\n".join(bits)
        sender = getattr(self.whatsapp, "send_reply_buttons", None)
        if callable(sender):
            return sender(
                mobile,
                body,
                [
                    {"id": f"BUY_INTERESTED {int(need['id'])} {seller_user_id}", "title": "👍 Interested"},
                    {"id": f"BUY_NOT_INTERESTED {int(need['id'])} {seller_user_id}", "title": "👎 Not now"},
                ],
            )
        return self.whatsapp.send_text_message(mobile, body)

    @staticmethod
    def _fingerprint(product: Dict[str, Any]) -> str:
        raw = "|".join(
            [
                str(product.get("subject") or "").casefold().strip(),
                str(product.get("brand") or "").casefold().strip(),
                str(product.get("variant") or "").casefold().strip(),
                str(product.get("price") if product.get("price") is not None else ""),
                str(product.get("stock_status") or "UNKNOWN").upper(),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _similarity(left: Any, right: Any) -> float:
        a = " ".join(str(left or "").casefold().split())
        b = " ".join(str(right or "").casefold().split())
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        if a in b or b in a:
            return 0.9
        at, bt = set(a.split()), set(b.split())
        if not at or not bt:
            return 0.0
        return len(at & bt) / len(at | bt)

    @staticmethod
    def _same_area(left: Any, right: Any) -> bool:
        a = " ".join(str(left or "").casefold().split())
        b = " ".join(str(right or "").casefold().split())
        return bool(a and b and (a in b or b in a))

    @staticmethod
    def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0088
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
        return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @staticmethod
    def _money(value: Any) -> str:
        try:
            number = float(value)
            return f"{number:,.0f}" if number.is_integer() else f"{number:,.2f}"
        except (TypeError, ValueError):
            return str(value)
