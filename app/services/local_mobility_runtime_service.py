"""Natural local Bike Taxi + Parcel request runtime."""
from __future__ import annotations

import math
import os
import re
from app.repositories.local_mobility_repository import LocalMobilityRepository


class LocalMobilityRuntimeService:
    RIDER_ON = {"rider on", "bike rider on", "parcel rider on", "local rider on", "రైడర్ ఆన్"}

    def __init__(self, db_path: str, user_repository, whatsapp_service) -> None:
        self.jobs = LocalMobilityRepository(db_path)
        self.users = user_repository
        self.whatsapp = whatsapp_service
        self.base_fare = float(os.getenv("PODX_LOCAL_BASE_FARE", "25"))
        self.per_km_fare = float(os.getenv("PODX_LOCAL_PER_KM_FARE", "10"))

    def process(self, sender_user_id: str, message: str) -> str | None:
        clean = " ".join(str(message or "").strip().split())
        lowered = clean.casefold()
        if lowered in self.RIDER_ON:
            return self._enable_rider(sender_user_id)

        customer_action = re.fullmatch(r"(?i)(?:MOB|LOCAL)\s+(CONFIRM|CANCEL|UNLOCK)\s+#?(\d+)", clean)
        if customer_action:
            verb, job_id = customer_action.group(1).upper(), int(customer_action.group(2))
            if verb == "CONFIRM": return self._confirm(sender_user_id, job_id)
            if verb == "CANCEL": return self._cancel(sender_user_id, job_id)
            return self._unlock(sender_user_id, job_id)

        action = re.fullmatch(r"(?i)(?:MOB|LOCAL)\s+(ACCEPT|PICKUP|ONWAY|DONE)\s+#?(\d+)", clean)
        if action:
            verb, job_id = action.group(1).upper(), int(action.group(2))
            if verb == "ACCEPT": return self._claim(sender_user_id, job_id)
            if verb == "PICKUP": return self._status(sender_user_id, job_id, "PICKED_UP")
            if verb == "ONWAY": return self._status(sender_user_id, job_id, "ON_THE_WAY")
            return self._status(sender_user_id, job_id, "COMPLETED")

        explicit = re.fullmatch(r"(?i)(BIKE|PARCEL)\s+(.+?)\s*\|\s*(.+?)(?:\s*\|\s*(.+))?", clean)
        if explicit:
            kind = explicit.group(1).upper()
            return self._create(sender_user_id, kind, explicit.group(2), explicit.group(3), explicit.group(4))

        parsed = self._parse_natural(clean)
        if parsed:
            return self._create(sender_user_id, parsed["type"], parsed["pickup"], parsed["drop"], parsed.get("note"), parsed.get("distance_km"))
        return None

    def _parse_natural(self, text: str):
        lower = text.casefold()
        bike_signal = any(x in lower for x in ("bike taxi", "bike ride", "bike కావాలి", "బైక్ కావాలి", "బైక్ టాక్సీ", "బైక్ రైడ్"))
        parcel_signal = any(x in lower for x in ("parcel", "పార్సెల్", "package పంప", "ప్యాకేజ్ పంప"))
        if not bike_signal and not parcel_signal:
            return None
        distance = self._extract_distance(text)
        route_text = re.sub(r"(?i)\b\d+(?:\.\d+)?\s*(?:km|kms|kilometers?|కిమీ)\b", "", text).strip(" ,-")
        route = re.search(r"(?i)(?:from\s+)?(.+?)\s+(?:to|నుంచి|నుండి)\s+(.+?)(?:\s+(?:కి|కు|పంపాలి|కావాలి|send|please))?$", route_text)
        if not route:
            route = re.search(r"(?i)(.+?)\s+నుంచి\s+(.+?)\s+(?:కి|కు)", route_text)
        if not route:
            return None
        pickup = route.group(1).strip()
        drop = route.group(2).strip()
        for prefix in ("bike taxi ", "bike ride ", "bike కావాలి ", "బైక్ కావాలి ", "parcel ", "పార్సెల్ "):
            if pickup.casefold().startswith(prefix.casefold()):
                pickup = pickup[len(prefix):].strip()
        if not pickup or not drop:
            return None
        return {"type": "PARCEL" if parcel_signal else "BIKE", "pickup": pickup, "drop": drop, "distance_km": distance}

    def _create(self, user_id: str, kind: str, pickup: str, drop: str, note: str | None = None, distance_km=None) -> str:
        user = self.users.find_by_whatsapp_mobile(str(user_id)) or {}
        if int(user.get("registration_complete") or 0) != 1:
            return "ముందుగా PODX registration complete చేయండి."
        if distance_km is None:
            distance_km = self._extract_distance(note or "")
        fare, fare_status = self._fare(distance_km)
        pickup_lat = user.get("latitude")
        pickup_lon = user.get("longitude")
        job_id = self.jobs.create(
            user_id, kind, pickup, drop, pickup_lat, pickup_lon, note,
            trip_distance_km=distance_km, fare_amount=fare, fare_status=fare_status,
        )
        label = "Bike Taxi" if kind == "BIKE" else "Parcel"
        if distance_km is not None:
            fare_line = f"Estimated distance: {distance_km:g} km\nEstimated fare: ₹{fare:.0f}"
        else:
            fare_line = f"Minimum/base fare: ₹{fare:.0f}\nExact road-distance fare ఇంకా pending."
        return (
            f"🧾 {label} request #{job_id}\nPickup: {pickup}\nDrop: {drop}\n{fare_line}\n\n"
            f"Ridersకి పంపడానికి MOB CONFIRM {job_id}\nCancel: MOB CANCEL {job_id}"
        )

    def _confirm(self, user_id: str, job_id: int) -> str:
        job = self.jobs.get(job_id) or {}
        if not job:
            return f"Request #{job_id} దొరకలేదు."
        if str(job.get("requester_user_id")) != str(user_id):
            return "ఈ requestని requester మాత్రమే confirm చేయగలరు."
        status = str(job.get("status") or "").upper()
        if status == "CANCELLED": return f"Request #{job_id} cancelled అయింది."
        if status != "DRAFT": return f"Request #{job_id} ఇప్పటికే confirmed అయింది."
        if not self.jobs.confirm(job_id, user_id):
            return f"Request #{job_id} confirm చేయలేకపోయాను."
        offered = self._offer(job_id)
        if offered:
            return f"✅ Request #{job_id} confirmed. Nearby ridersకి పంపాను; first accept చేసిన rider assign అవుతారు."
        return f"✅ Request #{job_id} confirmed. ప్రస్తుతం nearby rider దొరకలేదు; request openగా ఉంది."

    def _cancel(self, user_id: str, job_id: int) -> str:
        if self.jobs.cancel_draft(job_id, user_id):
            return f"✅ Request #{job_id} cancelled."
        return f"Request #{job_id} draftగా లేదు లేదా మీ request కాదు."

    def _unlock(self, user_id: str, job_id: int) -> str:
        job = self.jobs.get(job_id) or {}
        if not job:
            return f"Request #{job_id} దొరకలేదు."
        if str(job.get("requester_user_id")) != str(user_id):
            return "Contact unlock requesterకి మాత్రమే."
        rider_id = str(job.get("assigned_rider_id") or "")
        if not rider_id:
            return "Rider assign అయిన తర్వాత మాత్రమే contact unlock చేయవచ్చు."
        if not self.jobs.mark_unlocked(job_id, user_id):
            return "Contact unlock చేయలేకపోయాను."
        requester = self._contact(user_id)
        rider = self._contact(rider_id)
        self.whatsapp.send_text_message(
            self._mobile(rider_id),
            f"🔓 PODX local request #{job_id} customer contact unlocked.\nName: {requester['name']}\nPhone: {requester['phone']}"
        )
        return f"🔓 Rider contact unlocked.\nName: {rider['name']}\nPhone: {rider['phone']}\nRequest: #{job_id}"

    def _offer(self, job_id: int, radius_km: float = 12.0, limit: int = 12) -> int:
        job = self.jobs.get(job_id) or {}
        if str(job.get("status") or "").upper() != "OPEN":
            return 0
        rows = self.users.database.fetchall(
            """SELECT DISTINCT u.* FROM users u
               JOIN user_capabilities c ON c.whatsapp_mobile=u.whatsapp_mobile
               WHERE u.registration_complete=1
                 AND c.capability IN ('BIKE_RIDER','DELIVERY_PARTNER')
                 AND u.latitude IS NOT NULL AND u.longitude IS NOT NULL
               ORDER BY u.updated_at DESC"""
        )
        ranked = []
        for row in rows:
            rider = dict(row)
            rider_id = str(rider.get("whatsapp_mobile") or "")
            if not rider_id or rider_id == str(job.get("requester_user_id")):
                continue
            distance = self._distance(job.get("pickup_lat"), job.get("pickup_lon"), rider.get("latitude"), rider.get("longitude"))
            if distance is not None and distance > radius_km:
                continue
            ranked.append((distance if distance is not None else 9999.0, rider_id))
        ranked.sort(key=lambda x: x[0])
        sent = 0
        for distance_sort, rider_id in ranked[:limit]:
            distance = None if distance_sort >= 9999 else distance_sort
            if not self.jobs.offer(job_id, rider_id, distance):
                continue
            job = self.jobs.get(job_id) or {}
            kind = "🏍️ Bike Taxi" if job.get("job_type") == "BIKE" else "📦 Parcel"
            dist = f"\nPickup distance: {distance:.1f} km" if distance is not None else ""
            fare = f"\nCustomer fare estimate: ₹{float(job['fare_amount']):.0f}" if job.get("fare_amount") is not None else ""
            note = f"\nItem: {job.get('note')}" if job.get("note") else ""
            body = f"{kind} #{job_id}\nPickup: {job.get('pickup_text')}\nDrop: {job.get('drop_text')}{note}{dist}{fare}\nAccept: MOB ACCEPT {job_id}"
            self.whatsapp.send_reply_buttons(rider_id, body, [{"id": f"MOB ACCEPT {job_id}", "title": "Accept"}])
            sent += 1
        return sent

    def _enable_rider(self, user_id: str) -> str:
        user = self.users.find_by_whatsapp_mobile(str(user_id)) or {}
        if int(user.get("registration_complete") or 0) != 1:
            return "Riderగా join అవ్వడానికి ముందుగా PODX registration complete చేయండి."
        self.users.add_capability(str(user_id), "BIKE_RIDER", source="local_mobility")
        self.users.add_capability(str(user_id), "DELIVERY_PARTNER", source="local_mobility")
        if user.get("latitude") is None or user.get("longitude") is None:
            return "✅ Rider mode ON. Nearby Bike/Parcel requests పొందడానికి Current Location share చేయండి."
        return "✅ Rider mode ON. Nearby Bike Taxi/Parcel request వస్తే PODX notify చేస్తుంది."

    def _claim(self, rider_id: str, job_id: int) -> str:
        if not (self.users.has_capability(str(rider_id), "BIKE_RIDER") or self.users.has_capability(str(rider_id), "DELIVERY_PARTNER")):
            return "ముందుగా RIDER ON అని పంపి Rider mode enable చేయండి."
        if not self.jobs.claim(job_id, rider_id):
            job = self.jobs.get(job_id) or {}
            if job.get("assigned_rider_id"):
                return f"Request #{job_id} ఇప్పటికే మరో rider accept చేశారు."
            return f"Request #{job_id} మీకు availableగా లేదు."
        job = self.jobs.get(job_id) or {}
        requester = str(job.get("requester_user_id") or "")
        rider = self.users.find_by_whatsapp_mobile(str(rider_id)) or {}
        rider_name = str(rider.get("name") or "PODX Rider")
        self.whatsapp.send_text_message(
            self._mobile(requester),
            f"✅ {job.get('job_type')} request #{job_id}కి rider assigned: {rider_name}.\nPrivacy కోసం phone number hidden ఉంది. కావాలంటే MOB UNLOCK {job_id} పంపండి."
        )
        return f"✅ Request #{job_id} మీకు assign అయింది. Customer contact unlock చేస్తే PODX పంపుతుంది. Pickup తర్వాత MOB PICKUP {job_id} పంపండి."

    def _status(self, rider_id: str, job_id: int, status: str) -> str:
        if not self.jobs.update_status(job_id, rider_id, status):
            return f"Request #{job_id} status update చేయలేకపోయాను."
        job = self.jobs.get(job_id) or {}
        requester = self._mobile(str(job.get("requester_user_id") or ""))
        if status == "PICKED_UP":
            self.whatsapp.send_text_message(requester, f"📍 Request #{job_id}: rider pickup complete చేశారు.")
            return f"✅ Pickup saved. Next: MOB ONWAY {job_id}"
        if status == "ON_THE_WAY":
            self.whatsapp.send_text_message(requester, f"🏍️ Request #{job_id}: rider on the way.")
            return f"✅ On the way saved. Finish: MOB DONE {job_id}"
        self.whatsapp.send_text_message(requester, f"✅ Request #{job_id} completed.")
        return f"✅ Request #{job_id} completed."

    def _fare(self, distance_km):
        if distance_km is None:
            return self.base_fare, "MINIMUM_ONLY"
        distance = max(0.0, float(distance_km))
        return max(self.base_fare, self.base_fare + distance * self.per_km_fare), "ESTIMATED"

    @staticmethod
    def _extract_distance(text: str):
        match = re.search(r"(?i)\b(\d+(?:\.\d+)?)\s*(?:km|kms|kilometers?|కిమీ)\b", str(text or ""))
        return float(match.group(1)) if match else None

    def _contact(self, user_id: str):
        user = self.users.find_by_whatsapp_mobile(str(user_id)) or {}
        return {
            "name": str(user.get("name") or "PODX User"),
            "phone": str(user.get("entered_mobile") or user.get("whatsapp_mobile") or user_id),
        }

    def _mobile(self, user_id: str):
        user = self.users.find_by_whatsapp_mobile(str(user_id)) or {}
        return str(user.get("whatsapp_mobile") or user_id)

    @staticmethod
    def _distance(lat1, lon1, lat2, lon2):
        if None in {lat1, lon1, lat2, lon2}:
            return None
        try:
            p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
            dlat = p2 - p1
            dlon = math.radians(float(lon2) - float(lon1))
            a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
            return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))
        except (TypeError, ValueError):
            return None
