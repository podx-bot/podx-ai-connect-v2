"""WhatsApp ride-sharing runtime for driver posts and passenger seat requests."""
from __future__ import annotations

import re
from typing import Any


class RideRuntimeService:
    def __init__(self, repository, whatsapp_service, user_repository=None) -> None:
        self.rides = repository
        self.whatsapp = whatsapp_service
        self.users = user_repository

    def process(self, sender_user_id: str, message: str) -> str | None:
        clean = " ".join(str(message or "").strip().split())
        lowered = clean.casefold()
        if lowered.startswith("ride post "):
            return self._post(sender_user_id, clean[len("ride post "):])
        if lowered.startswith("ride find "):
            return self._find(clean[len("ride find "):])
        match = re.fullmatch(r"(?i)RIDE\s+BOOK\s+(\d+)(?:\s+(\d+))?", clean)
        if match:
            return self._book(sender_user_id, int(match.group(1)), int(match.group(2) or 1))
        match = re.fullmatch(r"(?i)RIDE\s+(ACCEPT|REJECT)\s+(\d+)", clean)
        if match:
            return self._decide(sender_user_id, int(match.group(2)), match.group(1).upper() == "ACCEPT")
        return None

    def _post(self, sender_user_id: str, payload: str) -> str:
        parts = [part.strip() for part in payload.split("|")]
        if len(parts) < 5:
            return "Format: RIDE POST <FROM> | <TO> | <DATE> | <TIME> | <SEATS> | <FARE optional>"
        origin, destination, travel_date, travel_time = parts[:4]
        try:
            seats = int(re.sub(r"[^0-9]", "", parts[4]))
        except ValueError:
            seats = 0
        if not origin or not destination or seats <= 0:
            return "From, To, seats సరైనగా ఇవ్వండి."
        fare = None
        if len(parts) > 5 and parts[5]:
            try:
                fare = float(re.sub(r"[^0-9.]", "", parts[5]))
            except ValueError:
                fare = None
        ride_id = self.rides.create_ride(sender_user_id, origin, destination, travel_date, travel_time, seats, fare)
        fare_text = f" • ₹{fare:g}/seat" if fare is not None else ""
        return f"✅ Ride #{ride_id} post అయింది.\n{origin} → {destination}\n{travel_date} • {travel_time} • {seats} seats{fare_text}"

    def _find(self, payload: str) -> str:
        parts = [part.strip() for part in payload.split("|")]
        if len(parts) < 3:
            return "Format: RIDE FIND <FROM> | <TO> | <DATE>"
        rides = self.rides.find_open(parts[0], parts[1], parts[2], limit=8)
        if not rides:
            return "ఈ route/dateకి ప్రస్తుతం open rides దొరకలేదు."
        lines = ["🚗 Available PODX rides:"]
        for ride in rides:
            fare = f" • ₹{float(ride['fare_per_seat']):g}/seat" if ride.get("fare_per_seat") is not None else ""
            lines.append(
                f"#{ride['id']} {ride['origin']} → {ride['destination']} | {ride['travel_date']} {ride['travel_time']} | {ride['seats_available']} seats{fare}"
            )
        lines.append("Seat request కోసం RIDE BOOK <Ride ID> పంపండి.")
        return "\n".join(lines)

    def _book(self, passenger_user_id: str, ride_id: int, seats: int) -> str:
        ride = self.rides.get_ride(ride_id)
        if not ride:
            return f"Ride #{ride_id} దొరకలేదు."
        if str(ride.get("driver_user_id")) == str(passenger_user_id):
            return "మీ own rideకి seat request చేయలేరు."
        result = self.rides.create_booking(ride_id, passenger_user_id, seats)
        status = result.get("status")
        if status == "ALREADY_REQUESTED":
            return "ఈ rideకి మీ seat request ఇప్పటికే pendingలో ఉంది."
        if status == "NOT_ENOUGH_SEATS":
            return "ఆ rideలో అంతమంది seats ప్రస్తుతం available లేవు."
        if status != "REQUESTED":
            return "ఈ ride ప్రస్తుతం bookingకి openగా లేదు."
        booking_id = int(result["booking_id"])
        driver_mobile = self._mobile(str(ride["driver_user_id"]))
        passenger_name = self._name(passenger_user_id, "Passenger")
        self.whatsapp.send_text_message(
            driver_mobile,
            "🚗 PODX Seat Request\n"
            f"Booking: #{booking_id}\nRide: #{ride_id} {ride['origin']} → {ride['destination']}\n"
            f"Passenger: {passenger_name}\nSeats: {seats}\n\n"
            f"Accept: RIDE ACCEPT {booking_id}\nReject: RIDE REJECT {booking_id}",
        )
        return f"✅ Seat request #{booking_id} driverకి పంపాను. Driver confirmation వచ్చిన తర్వాత seat confirm అవుతుంది."

    def _decide(self, driver_user_id: str, booking_id: int, accept: bool) -> str:
        booking = self.rides.get_booking(booking_id)
        if not booking:
            return f"Seat request #{booking_id} దొరకలేదు."
        result = self.rides.decide_booking(booking_id, driver_user_id, accept)
        status = result.get("status")
        if status == "NOT_DRIVER":
            return "ఈ ride మీది కాదు."
        if status == "NOT_ENOUGH_SEATS":
            return "ఇప్పుడు required seats available లేవు."
        if status in {"ACCEPTED", "REJECTED"}:
            passenger_mobile = self._mobile(str(booking["passenger_user_id"]))
            ride = result.get("ride") or self.rides.get_ride(int(booking["ride_id"])) or {}
            if status == "ACCEPTED":
                self.whatsapp.send_text_message(
                    passenger_mobile,
                    "✅ మీ PODX ride seat request accept అయింది.\n"
                    f"Ride #{ride.get('id')} {ride.get('origin')} → {ride.get('destination')}\n"
                    f"Date/Time: {ride.get('travel_date')} {ride.get('travel_time')}\n"
                    f"Seats: {booking['seats']}",
                )
                return f"✅ Seat request #{booking_id} accept అయింది. Remaining seats: {ride.get('seats_available')}."
            self.whatsapp.send_text_message(passenger_mobile, f"Ride seat request #{booking_id} driver reject చేశారు.")
            return f"Seat request #{booking_id} reject చేశాను."
        if status in {"ACCEPTED", "REJECTED"}:
            return f"Seat request #{booking_id} ఇప్పటికే {status.lower()} అయింది."
        return f"Seat request #{booking_id} update చేయలేకపోయాను."

    def _mobile(self, user_id: str) -> str:
        if self.users is None:
            return str(user_id)
        user = self.users.find_by_whatsapp_mobile(str(user_id)) or {}
        return str(user.get("whatsapp_mobile") or user_id)

    def _name(self, user_id: str, fallback: str) -> str:
        if self.users is None:
            return fallback
        user = self.users.find_by_whatsapp_mobile(str(user_id)) or {}
        return str(user.get("name") or fallback)
