"""Route-aware wrapper around the existing ride runtime."""
from __future__ import annotations

import re

from app.services.local_mobility_runtime_service import LocalMobilityRuntimeService


class RideRouteRuntimeService:
    def __init__(self, ride_runtime, route_service, mobility_runtime=None) -> None:
        self.ride_runtime = ride_runtime
        self.route = route_service
        users = getattr(ride_runtime, "users", None)
        whatsapp = getattr(ride_runtime, "whatsapp", None)
        db_path = getattr(getattr(ride_runtime, "rides", None), "db_path", "podx.db")
        self.mobility = mobility_runtime or (
            LocalMobilityRuntimeService(db_path, users, whatsapp)
            if users is not None and whatsapp is not None else None
        )

    def process(self, sender_user_id: str, message: str) -> str | None:
        clean = " ".join(str(message or "").strip().split())
        lowered = clean.casefold()

        if self.mobility is not None:
            mobility_reply = self.mobility.process(sender_user_id, clean)
            if mobility_reply is not None:
                return mobility_reply

        stops = re.match(r"(?i)^RIDE\s+STOPS\s+(\d+)\s*\|\s*(.+)$", clean)
        if stops:
            ride_id = int(stops.group(1))
            specs = [x.strip() for x in stops.group(2).split("|") if x.strip()]
            result = self.route.set_stops(ride_id, sender_user_id, specs)
            if result.get("status") == "NOT_FOUND":
                return f"Ride #{ride_id} దొరకలేదు."
            if result.get("status") == "NOT_DRIVER":
                return "ఈ ride మీది కాదు."
            names = " → ".join(str(p["name"]) for p in result.get("points", []))
            return f"✅ Ride #{ride_id} route stops save అయ్యాయి.\n{names}"

        if lowered.startswith("ride find "):
            payload = clean[len("ride find "):]
            return self._find(sender_user_id, payload)

        if lowered.startswith("ride "):
            return self.ride_runtime.process(sender_user_id, clean)

        intake = getattr(self.ride_runtime, "natural_intake", None)
        if intake is not None:
            parsed = intake.process(str(sender_user_id), clean)
            if parsed is not None:
                if parsed.get("reply"):
                    return str(parsed["reply"])
                if parsed.get("action") == "FIND":
                    return self._find(
                        sender_user_id,
                        " | ".join([
                            str(parsed["origin"]),
                            str(parsed["destination"]),
                            str(parsed["travel_date"]),
                        ]),
                    )
                if parsed.get("action") == "POST":
                    fare = parsed.get("fare")
                    parts = [
                        str(parsed["origin"]), str(parsed["destination"]),
                        str(parsed["travel_date"]), str(parsed["travel_time"]),
                        str(parsed["seats"]),
                    ]
                    if fare is not None:
                        parts.append(str(fare))
                    reply = self.ride_runtime._post(sender_user_id, " | ".join(parts))
                    ride_id = self._extract_ride_id(reply)
                    if ride_id:
                        ride = self.ride_runtime.rides.get_ride(ride_id) or {}
                        self.route.initialize_route(
                            ride_id,
                            str(ride.get("origin") or parsed["origin"]),
                            str(ride.get("destination") or parsed["destination"]),
                            str(sender_user_id),
                        )
                    return reply

        return self.ride_runtime.process(sender_user_id, clean)

    def _find(self, passenger_user_id: str, payload: str) -> str:
        parts = [p.strip() for p in payload.split("|")]
        if len(parts) < 3:
            return "Format: RIDE FIND <FROM> | <TO> | <DATE>"
        matches = self.route.find_subroute(passenger_user_id, parts[0], parts[1], parts[2], limit=8)
        if not matches:
            return "ఈ route/dateకి ప్రస్తుతం open rides దొరకలేదు."
        lines = ["🚗 Route-matched PODX rides:"]
        for ride in matches:
            fare = f" • ₹{float(ride['fare_per_seat']):g}/seat" if ride.get("fare_per_seat") is not None else ""
            near = f" • pickup ~{ride['pickup_distance_km']:g} km" if ride.get("pickup_distance_km") is not None else ""
            lines.append(
                f"#{ride['id']} {ride['pickup_name']} → {ride['drop_name']} | "
                f"{ride['travel_date']} {ride['travel_time']} | {ride['seats_available']} seats{fare}{near}"
            )
        lines.append("Book ride <Ride ID> అని పంపండి.")
        return "\n".join(lines)

    @staticmethod
    def _extract_ride_id(reply: str | None) -> int | None:
        m = re.search(r"Ride\s+#(\d+)", str(reply or ""), re.I)
        return int(m.group(1)) if m else None
