"""Non-blocking ride final-fare confirmation and zero-charge settlement wrapper."""
from __future__ import annotations

import re

from app.repositories.ride_settlement_repository import RideSettlementRepository


class RideSettlementRuntimeService:
    def __init__(self, delegate, ride_repository, whatsapp_service=None, user_repository=None, settlement_repository=None) -> None:
        self.delegate = delegate
        self.rides = ride_repository
        self.whatsapp = whatsapp_service
        self.users = user_repository
        self.settlements = settlement_repository or RideSettlementRepository(
            getattr(ride_repository, "db_path", "podx.db")
        )

    def process(self, sender_user_id: str, message: str) -> str | None:
        clean = " ".join(str(message or "").strip().split())

        proposed = re.fullmatch(r"(?i)RIDE\s+FINAL\s+(\d+)\s*\|\s*₹?\s*([0-9]+(?:\.[0-9]+)?)", clean)
        if proposed:
            return self._propose(sender_user_id, int(proposed.group(1)), float(proposed.group(2)))

        confirmed = re.fullmatch(r"(?i)RIDE\s+FINAL\s+OK\s+(\d+)", clean)
        if confirmed:
            return self._confirm(sender_user_id, int(confirmed.group(1)))

        status = re.fullmatch(r"(?i)RIDE\s+SETTLEMENT\s+(\d+)", clean)
        if status:
            return self._status(sender_user_id, int(status.group(1)))

        done = re.fullmatch(r"(?i)RIDE\s+DONE\s+(\d+)", clean)
        reply = self.delegate.process(sender_user_id, clean)
        if done and reply and "completed" in reply.casefold():
            booking_id = int(done.group(1))
            self._ensure(booking_id)
            self.settlements.mark_completed(booking_id)
        return reply

    def _ensure(self, booking_id: int):
        booking = self.rides.get_booking(booking_id)
        if not booking:
            return None, None, None
        ride = self.rides.get_ride(int(booking["ride_id"]))
        if not ride:
            return booking, None, None
        settlement = self.settlements.ensure(booking, ride)
        return booking, ride, settlement

    def _propose(self, sender_user_id: str, booking_id: int, amount: float) -> str:
        booking, ride, _ = self._ensure(booking_id)
        if not booking or not ride:
            return f"Booking #{booking_id} దొరకలేదు."
        if str(ride.get("driver_user_id")) != str(sender_user_id):
            return "Final fare ఈ ride driver మాత్రమే set చేయగలరు."
        if str(booking.get("status")).upper() not in {"ACCEPTED", "COMPLETED"}:
            return "Accepted/completed bookingకి మాత్రమే final fare set చేయవచ్చు."
        result = self.settlements.propose_final_fare(booking_id, amount)
        if not result:
            return "Final fare save చేయలేకపోయాను."
        passenger = self._mobile(str(booking.get("passenger_user_id") or ""))
        if passenger and self.whatsapp is not None:
            self.whatsapp.send_text_message(
                passenger,
                f"🚗 Ride booking #{booking_id} final fare: ₹{float(result['final_fare']):g}.\n"
                f"PODX platform charge: ₹0.\nConfirm చేయడానికి RIDE FINAL OK {booking_id} పంపండి.",
            )
        return f"✅ Booking #{booking_id} final fare ₹{float(result['final_fare']):g} save అయింది. PODX charge ₹0."

    def _confirm(self, sender_user_id: str, booking_id: int) -> str:
        booking, ride, settlement = self._ensure(booking_id)
        if not booking or not ride or not settlement:
            return f"Booking #{booking_id} దొరకలేదు."
        if str(booking.get("passenger_user_id")) != str(sender_user_id):
            return "Final fare confirmation ఈ booking passengerకి మాత్రమే."
        if settlement.get("final_fare") is None:
            return "Driver final fare ఇంకా set చేయలేదు."
        result = self.settlements.confirm_final_fare(booking_id)
        if not result:
            return "Final fare confirm చేయలేకపోయాను."
        return f"✅ Booking #{booking_id} final fare ₹{float(result['final_fare']):g} confirmed. PODX platform charge ₹0."

    def _status(self, sender_user_id: str, booking_id: int) -> str:
        booking, ride, settlement = self._ensure(booking_id)
        if not booking or not ride or not settlement:
            return f"Booking #{booking_id} దొరకలేదు."
        allowed = {str(booking.get("passenger_user_id")), str(ride.get("driver_user_id"))}
        if str(sender_user_id) not in allowed:
            return "ఈ settlement details booking passenger/driverకి మాత్రమే."
        final_fare = settlement.get("final_fare")
        fare_text = "not set" if final_fare is None else f"₹{float(final_fare):g}"
        return (
            f"Ride settlement #{booking_id}\n"
            f"Final fare: {fare_text}\n"
            f"PODX platform charge: ₹0\n"
            f"Status: {settlement.get('status')}"
        )

    def _mobile(self, user_id: str) -> str:
        if self.users is None:
            return str(user_id)
        user = self.users.find_by_whatsapp_mobile(str(user_id)) or {}
        return str(user.get("whatsapp_mobile") or user_id)
