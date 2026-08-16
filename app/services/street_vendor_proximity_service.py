"""Targeted proximity alerts for active street/mobile vendors."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Optional


class StreetVendorProximityService:
    def __init__(self, repository, demand_repository, user_repository, whatsapp_service,
                 radius_km: float = 1.5, repeat_after_hours: float = 2.0,
                 meaningful_move_km: float = 0.5, alert_preferences=None) -> None:
        self.repository = repository
        self.demands = demand_repository
        self.users = user_repository
        self.whatsapp = whatsapp_service
        self.radius_km = float(radius_km)
        self.repeat_after = timedelta(hours=float(repeat_after_hours))
        self.meaningful_move_km = float(meaningful_move_km)
        self.alert_preferences = alert_preferences or self._auto_alert_preferences(repository)

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

    def process_text(self, sender_mobile: str, message: str) -> Optional[str]:
        clean = " ".join(str(message or "").strip().split())
        upper = clean.upper()
        if upper == "VENDOR OFF":
            self.repository.disable(sender_mobile)
            return "✅ Mobile vendor alerts off చేశాం."
        match = re.fullmatch(r"VENDOR ON(?:\s+(.+))?", clean, re.IGNORECASE)
        if match:
            items = str(match.group(1) or "").strip()
            if not items:
                return "మీరు mobileగా అమ్మే items చెప్పండి. Example: VENDOR ON vegetables, fruits"
            self.repository.enable(sender_mobile, items)
            return "✅ Mobile vendor mode ON. ఇప్పుడు మీ current location share చేయండి లేదా `VENDOR HERE <lat>,<lon>` పంపండి."
        match = re.fullmatch(r"VENDOR HERE\s+(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)", clean, re.IGNORECASE)
        if match:
            return self.handle_location(sender_mobile, float(match.group(1)), float(match.group(2)))
        if upper == "VENDOR STATUS":
            profile = self.repository.get(sender_mobile)
            if not profile:
                return "Mobile vendor mode ఇంకా setup కాలేదు."
            return (
                f"Vendor status: {profile.get('status')}\n"
                f"Items: {profile.get('items_text') or '-'}\n"
                f"Location updated: {profile.get('last_location_at') or '-'}"
            )
        return None

    def handle_shared_location(self, vendor_mobile: str, latitude: float, longitude: float) -> Optional[str]:
        profile = self.repository.get(vendor_mobile)
        if not profile or str(profile.get("status") or "").upper() != "ACTIVE":
            return None
        return self.handle_location(vendor_mobile, latitude, longitude)

    def handle_location(self, vendor_mobile: str, latitude: float, longitude: float) -> str:
        profile = self.repository.update_location(vendor_mobile, latitude, longitude)
        if not profile:
            return "ముందుగా `VENDOR ON <items>` పంపండి. తర్వాత location share చేయండి."
        alerted = self._notify_relevant_buyers(profile)
        if alerted:
            return f"📍 Vendor location updated. Nearby interested customersలో {alerted} మందికి targeted alert పంపాం."
        return "📍 Vendor location updated. ప్రస్తుతం nearby matching customer demand లేదు."

    def _notify_relevant_buyers(self, profile: dict) -> int:
        items_text = str(profile.get("items_text") or "").strip()
        if not items_text:
            return 0
        vendor_lat = float(profile["latitude"])
        vendor_lon = float(profile["longitude"])
        vendor_mobile = str(profile["vendor_mobile"])
        sent = 0
        for demand in self.demands.list_active(limit=500, exclude_user_id=vendor_mobile):
            if str(demand.get("side") or "").upper() != "NEED":
                continue
            if str(demand.get("domain") or "").upper() != "PRODUCT":
                continue
            subject = str(demand.get("subject") or "").strip()
            if not self._subject_match(items_text, subject):
                continue
            buyer_mobile = str(demand.get("user_id") or "").strip()
            if self.alert_preferences is not None and not self.alert_preferences.is_enabled(buyer_mobile):
                continue
            buyer_lat, buyer_lon = self._buyer_location(demand, buyer_mobile)
            if buyer_lat is None or buyer_lon is None:
                continue
            distance = self._distance_km(vendor_lat, vendor_lon, buyer_lat, buyer_lon)
            if distance > self.radius_km:
                continue
            if not self._should_alert(vendor_mobile, buyer_mobile, int(demand["id"]), vendor_lat, vendor_lon):
                continue
            message = (
                f"🛒 Nearby mobile seller alert\n\n"
                f"మీరు వెతికిన: {subject}\n"
                f"Mobile seller సుమారు {distance:.1f} km దూరంలో ఉన్నారు.\n"
                "అవసరం ఉంటే PODXలో interested అని reply చేయండి."
            )
            try:
                self.whatsapp.send_text_message(recipient_mobile=buyer_mobile, message=message)
            except Exception:
                continue
            self.repository.save_alert(vendor_mobile, buyer_mobile, int(demand["id"]), subject, vendor_lat, vendor_lon)
            sent += 1
        return sent

    def _buyer_location(self, demand: dict, buyer_mobile: str) -> tuple[float | None, float | None]:
        if demand.get("latitude") is not None and demand.get("longitude") is not None:
            return float(demand["latitude"]), float(demand["longitude"])
        user = self.users.find_by_whatsapp_mobile(buyer_mobile) or {}
        if user.get("latitude") is None or user.get("longitude") is None:
            return None, None
        return float(user["latitude"]), float(user["longitude"])

    def _should_alert(self, vendor_mobile: str, buyer_mobile: str, demand_id: int,
                      latitude: float, longitude: float) -> bool:
        existing = self.repository.alert_record(vendor_mobile, buyer_mobile, demand_id)
        if not existing:
            return True
        try:
            alerted_at = datetime.fromisoformat(str(existing["alerted_at"]))
            if alerted_at.tzinfo is None:
                alerted_at = alerted_at.replace(tzinfo=timezone.utc)
        except Exception:
            return True
        old_lat = existing.get("vendor_latitude")
        old_lon = existing.get("vendor_longitude")
        moved = 0.0
        if old_lat is not None and old_lon is not None:
            moved = self._distance_km(float(old_lat), float(old_lon), latitude, longitude)
        return datetime.now(timezone.utc) - alerted_at >= self.repeat_after or moved >= self.meaningful_move_km

    @staticmethod
    def _subject_match(items_text: str, subject: str) -> bool:
        def tokens(value: str) -> set[str]:
            return {x for x in re.findall(r"[\w\u0C00-\u0C7F]+", value.casefold()) if len(x) > 1}
        item_tokens = tokens(items_text)
        subject_tokens = tokens(subject)
        if not item_tokens or not subject_tokens:
            return False
        if subject.casefold() in items_text.casefold() or items_text.casefold() in subject.casefold():
            return True
        return bool(item_tokens & subject_tokens)

    @staticmethod
    def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        earth = 6371.0088
        p1, p2 = radians(lat1), radians(lat2)
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(p1) * cos(p2) * sin(dlon / 2) ** 2
        return 2 * earth * asin(sqrt(a))
