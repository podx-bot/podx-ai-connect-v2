"""WhatsApp ride-sharing runtime for posts, seats, contact unlock and completion."""
from __future__ import annotations
import os
import re

from app.services.ride_natural_intake_service import RideNaturalIntakeService

class RideRuntimeService:
    DRIVER_ACCEPT_WORDS={"accept","accept చేయి","accept cheyi","యాక్సెప్ట్","అక్సెప్ట్","स्वीकार","accept it"}
    DRIVER_REJECT_WORDS={"reject","reject చేయి","reject cheyi","రిజెక్ట్","अस्वीकार","reject it"}

    def __init__(self, repository, whatsapp_service, user_repository=None, admin_mobile: str | None = None, natural_intake=None) -> None:
        self.rides=repository; self.whatsapp=whatsapp_service; self.users=user_repository
        self.natural_intake=natural_intake or RideNaturalIntakeService(getattr(repository,'db_path','podx.db'))
        self.admin_mobile=str(admin_mobile or os.getenv('PODX_ADMIN_MOBILE') or '').strip()

    def process(self,sender_user_id:str,message:str)->str|None:
        clean=" ".join(str(message or "").strip().split()); lowered=clean.casefold()
        payment=re.fullmatch(r"(?i)RIDE\s+PAYMENT\s+OK\s+(\d+)\s*\|\s*(.+)",clean)
        if payment:return self._authorize_payment(sender_user_id,int(payment.group(1)),payment.group(2).strip())
        unlock=re.fullmatch(r"(?i)RIDE\s+UNLOCK\s+(\d+)",clean)
        if unlock:return self._unlock(sender_user_id,int(unlock.group(1)))
        done=re.fullmatch(r"(?i)RIDE\s+DONE\s+(\d+)",clean)
        if done:return self._complete(sender_user_id,int(done.group(1)))
        if lowered.startswith("ride post "):return self._post(sender_user_id,clean[len("ride post "):])
        if lowered.startswith("ride find "):return self._find(clean[len("ride find "):])
        match=re.fullmatch(r"(?i)RIDE\s+BOOK\s+(\d+)(?:\s+(\d+))?",clean)
        if match:return self._book(sender_user_id,int(match.group(1)),int(match.group(2) or 1))
        match=re.fullmatch(r"(?i)RIDE\s+(ACCEPT|REJECT)\s+(\d+)",clean)
        if match:return self._decide(sender_user_id,int(match.group(2)),match.group(1).upper()=="ACCEPT")

        natural_book=re.fullmatch(r"(?i)(?:book\s+ride|ride\s+book|ride\s+బుక్|బుక్\s+ride|राइड\s+बुक|बुक\s+राइड)\s*#?(\d+)(?:\s*[,|-]?\s*(\d+)\s*(?:seats?|సీట్లు|సీట్స్|सीट|सीटें))?",clean)
        if natural_book:return self._book(sender_user_id,int(natural_book.group(1)),int(natural_book.group(2) or 1))

        if lowered in self.DRIVER_ACCEPT_WORDS or lowered in self.DRIVER_REJECT_WORDS:
            pending=self.rides.latest_requested_booking_for_driver(sender_user_id)
            if pending is not None:
                return self._decide(sender_user_id,int(pending['id']),lowered in self.DRIVER_ACCEPT_WORDS)

        if self.natural_intake is not None:
            intake=self.natural_intake.process(str(sender_user_id),clean)
            if intake is not None:
                if intake.get('reply'):return str(intake['reply'])
                if intake.get('action')=='POST':
                    fare=intake.get('fare'); parts=[str(intake['origin']),str(intake['destination']),str(intake['travel_date']),str(intake['travel_time']),str(intake['seats'])]
                    if fare is not None:parts.append(str(fare))
                    return self._post(sender_user_id,' | '.join(parts))
                if intake.get('action')=='FIND':
                    return self._find(' | '.join([str(intake['origin']),str(intake['destination']),str(intake['travel_date'])]))
        return None

    def _post(self,sender_user_id,payload):
        parts=[p.strip() for p in payload.split('|')]
        if len(parts)<5:return "Format: RIDE POST <FROM> | <TO> | <DATE> | <TIME> | <SEATS> | <FARE optional>"
        origin,destination,travel_date,travel_time=parts[:4]
        try:seats=int(re.sub(r'[^0-9]','',parts[4]))
        except ValueError:seats=0
        if not origin or not destination or seats<=0:return "From, To, seats సరైనగా ఇవ్వండి."
        fare=None
        if len(parts)>5 and parts[5]:
            try:fare=float(re.sub(r'[^0-9.]','',parts[5]))
            except ValueError:fare=None
        ride_id=self.rides.create_ride(sender_user_id,origin,destination,travel_date,travel_time,seats,fare); fare_text=f" • ₹{fare:g}/seat" if fare is not None else ''
        return f"✅ Ride #{ride_id} post అయింది.\n{origin} → {destination}\n{travel_date} • {travel_time} • {seats} seats{fare_text}"

    def _find(self,payload):
        parts=[p.strip() for p in payload.split('|')]
        if len(parts)<3:return "Format: RIDE FIND <FROM> | <TO> | <DATE>"
        rides=self.rides.find_open(parts[0],parts[1],parts[2],limit=8)
        if not rides:return "ఈ route/dateకి ప్రస్తుతం open rides దొరకలేదు."
        lines=['🚗 Available PODX rides:']
        for ride in rides:
            fare=f" • ₹{float(ride['fare_per_seat']):g}/seat" if ride.get('fare_per_seat') is not None else ''
            lines.append(f"#{ride['id']} {ride['origin']} → {ride['destination']} | {ride['travel_date']} {ride['travel_time']} | {ride['seats_available']} seats{fare}")
        lines.append('Seat request కోసం “Book ride <Ride ID>” అని పంపండి. ఉదా: Book ride 12, 2 seats.');return '\n'.join(lines)

    def _book(self,passenger_user_id,ride_id,seats):
        ride=self.rides.get_ride(ride_id)
        if not ride:return f"Ride #{ride_id} దొరకలేదు."
        if str(ride.get('driver_user_id'))==str(passenger_user_id):return "మీ own rideకి seat request చేయలేరు."
        result=self.rides.create_booking(ride_id,passenger_user_id,seats);status=result.get('status')
        if status=='ALREADY_REQUESTED':return "ఈ rideకి మీ seat request ఇప్పటికే pendingలో ఉంది."
        if status=='NOT_ENOUGH_SEATS':return "ఆ rideలో అంతమంది seats ప్రస్తుతం available లేవు."
        if status!='REQUESTED':return "ఈ ride ప్రస్తుతం bookingకి openగా లేదు."
        booking_id=int(result['booking_id']);driver_mobile=self._mobile(str(ride['driver_user_id']));passenger_name=self._name(passenger_user_id,'Passenger')
        self.whatsapp.send_text_message(driver_mobile,"🚗 PODX Seat Request\n"+f"Booking: #{booking_id}\nRide: #{ride_id} {ride['origin']} → {ride['destination']}\n"+f"Passenger: {passenger_name}\nSeats: {seats}\n\n"+"Reply Accept లేదా Reject.\n"+f"Commands కూడా పని చేస్తాయి: RIDE ACCEPT {booking_id} / RIDE REJECT {booking_id}")
        return f"✅ Seat request #{booking_id} driverకి పంపాను. Driver confirmation వచ్చిన తర్వాత seat confirm అవుతుంది."

    def _decide(self,driver_user_id,booking_id,accept):
        booking=self.rides.get_booking(booking_id)
        if not booking:return f"Seat request #{booking_id} దొరకలేదు."
        result=self.rides.decide_booking(booking_id,driver_user_id,accept);status=result.get('status')
        if status=='NOT_DRIVER':return "ఈ ride మీది కాదు."
        if status=='NOT_ENOUGH_SEATS':return "ఇప్పుడు required seats available లేవు."
        if status in {'ACCEPTED','REJECTED'} and 'booking' not in result:return f"Seat request #{booking_id} ఇప్పటికే {status.lower()} అయింది."
        if status in {'ACCEPTED','REJECTED'}:
            passenger_mobile=self._mobile(str(booking['passenger_user_id']));ride=result.get('ride') or self.rides.get_ride(int(booking['ride_id'])) or {}
            if status=='ACCEPTED':
                self.whatsapp.send_text_message(passenger_mobile,"✅ మీ PODX ride seat request accept అయింది.\n"+f"Ride #{ride.get('id')} {ride.get('origin')} → {ride.get('destination')}\n"+f"Date/Time: {ride.get('travel_date')} {ride.get('travel_time')}\nSeats: {booking['seats']}\n\nContact unlock ready. RIDE UNLOCK {booking_id} పంపండి.")
                return f"✅ Seat request #{booking_id} accept అయింది. Remaining seats: {ride.get('seats_available')}."
            self.whatsapp.send_text_message(passenger_mobile,f"Ride seat request #{booking_id} driver reject చేశారు.");return f"Seat request #{booking_id} reject చేశాను."
        return f"Seat request #{booking_id} update చేయలేకపోయాను."

    def _authorize_payment(self,sender_user_id,booking_id,payment_ref):
        if not self.admin_mobile or str(sender_user_id)!=self.admin_mobile:return "ఈ payment authorization command admin/internal useకి మాత్రమే."
        if not self.rides.authorize_unlock(booking_id,'PODX_FREE',0.0):return "Accepted booking దొరకలేదు; unlock authorize చేయలేదు."
        return f"✅ Ride booking #{booking_id} contact unlock ready. Payment gateway is disabled."

    def _unlock(self,sender_user_id,booking_id):
        booking=self.rides.get_booking(booking_id)
        if not booking:return f"Booking #{booking_id} దొరకలేదు."
        if str(booking.get('passenger_user_id'))!=str(sender_user_id):return "Contact unlock ఈ booking passengerకి మాత్రమే."
        if str(booking.get('status')).upper() not in {'ACCEPTED','COMPLETED'}:return "Driver seat accept చేసిన తర్వాత మాత్రమే contact unlock చేయవచ్చు."
        unlock=self.rides.get_unlock(booking_id) or {}
        if str(unlock.get('payment_status')).upper() not in {'FREE','PAID'}:
            if not self.rides.authorize_unlock(booking_id,'PODX_FREE',0.0):return f"Booking #{booking_id} contact unlock ప్రస్తుతం available లేదు."
        ride=self.rides.get_ride(int(booking['ride_id'])) or {}; driver_id=str(ride.get('driver_user_id') or '')
        driver=self._contact(driver_id); passenger=self._contact(str(sender_user_id)); self.rides.mark_unlocked(booking_id)
        driver_text=f"Name: {driver['name']}\nPhone: {driver['phone']}"; passenger_text=f"Name: {passenger['name']}\nPhone: {passenger['phone']}"
        self.whatsapp.send_text_message(self._mobile(driver_id),f"🔓 PODX Ride #{ride.get('id')} passenger contact unlocked.\n{passenger_text}\nBooking: #{booking_id}")
        return f"🔓 Driver contact unlocked.\n{driver_text}\nRide: {ride.get('origin')} → {ride.get('destination')}\nBooking: #{booking_id}"

    def _complete(self,sender_user_id,booking_id):
        result=self.rides.complete_booking(booking_id,sender_user_id);status=result.get('status')
        if status=='NOT_DRIVER':return "ఈ ride మీది కాదు."
        if status=='NOT_ACCEPTED':return "Accepted booking మాత్రమే complete చేయవచ్చు."
        if status=='NOT_FOUND':return f"Booking #{booking_id} దొరకలేదు."
        if status=='COMPLETED' and 'booking' not in result:return f"✅ Booking #{booking_id} ఇప్పటికే completed అయింది."
        booking=result.get('booking') or {}; passenger=self._mobile(str(booking.get('passenger_user_id') or ''))
        if passenger:self.whatsapp.send_text_message(passenger,f"✅ Ride booking #{booking_id} completed. PODXని ఉపయోగించినందుకు ధన్యవాదాలు.")
        return f"✅ Ride booking #{booking_id} completedగా mark అయింది."

    def _contact(self,user_id):
        if self.users is None:return {'name':'PODX User','phone':str(user_id)}
        user=self.users.find_by_whatsapp_mobile(str(user_id)) or {};return {'name':str(user.get('name') or 'PODX User'),'phone':str(user.get('entered_mobile') or user.get('whatsapp_mobile') or user_id)}
    def _mobile(self,user_id):
        if self.users is None:return str(user_id)
        user=self.users.find_by_whatsapp_mobile(str(user_id)) or {};return str(user.get('whatsapp_mobile') or user_id)
    def _name(self,user_id,fallback):
        if self.users is None:return fallback
        user=self.users.find_by_whatsapp_mobile(str(user_id)) or {};return str(user.get('name') or fallback)
