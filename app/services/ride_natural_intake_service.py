"""Deterministic multilingual natural-language intake for PODX ride sharing."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Any


class RideNaturalIntakeService:
    DRIVER_MARKERS = (
        "seats available", "seat available", "empty seats", "i am driving", "i'm driving",
        "i am going", "i'm going", "travelling", "traveling", "వెళ్తున్నాను", "వెళ్తున్నా",
        "వెళ్ళుతున్నాను", "వెళ్లుతున్నాను", "సీట్లు ఉన్నాయి", "seats ఉన్నాయి", "నా car",
        "मेरी car", "जा रहा हूं", "जा रही हूं", "सीट खाली", "seats खाली",
    )
    PASSENGER_MARKERS = (
        "need a ride", "ride కావాలి", "ride కావలెను", "seat కావాలి", "car కావాలి",
        "ride चाहिए", "seat चाहिए", "सवारी चाहिए", "lift కావాలి", "lift चाहिए",
        "ride need", "looking for ride", "ride వెతుకుతున్నాను", "ride వెతుకుతున్నా",
    )
    CANCEL_WORDS = {"cancel ride", "ride cancel", "cancel", "stop ride", "వద్దు", "క్యాన్సిల్", "रद्द"}

    def __init__(self, db_path: str = "podx.db") -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ride_natural_intake (
                    user_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    origin TEXT,
                    destination TEXT,
                    travel_date TEXT,
                    travel_time TEXT,
                    seats INTEGER,
                    fare REAL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def process(self, user_id: str, message: str) -> dict[str, Any] | None:
        clean = " ".join(str(message or "").strip().split())
        if not clean:
            return None
        lowered = clean.casefold()
        pending = self._get(str(user_id))
        if pending and lowered in self.CANCEL_WORDS:
            self._clear(str(user_id))
            return {"reply": "✅ Ride flow cancel చేశాను."}

        if pending:
            mode = str(pending["mode"])
            fields = {k: pending.get(k) for k in ("origin", "destination", "travel_date", "travel_time", "seats", "fare")}
            self._merge(fields, self._extract(clean, mode=mode, follow_up=True))
            return self._finish_or_prompt(str(user_id), mode, fields)

        mode = self._detect_mode(clean)
        if mode is None:
            return None
        fields = self._extract(clean, mode=mode, follow_up=False)
        return self._finish_or_prompt(str(user_id), mode, fields)

    def _finish_or_prompt(self, user_id: str, mode: str, fields: dict[str, Any]) -> dict[str, Any]:
        required = ["origin", "destination", "travel_date"]
        if mode == "DRIVER":
            required += ["travel_time", "seats"]
        missing = [key for key in required if not fields.get(key)]
        if missing:
            self._save(user_id, mode, fields)
            return {"reply": self._prompt(mode, missing[0], fields)}

        self._clear(user_id)
        if mode == "DRIVER":
            return {
                "action": "POST",
                "origin": fields["origin"],
                "destination": fields["destination"],
                "travel_date": fields["travel_date"],
                "travel_time": fields["travel_time"],
                "seats": int(fields["seats"]),
                "fare": fields.get("fare"),
            }
        return {
            "action": "FIND",
            "origin": fields["origin"],
            "destination": fields["destination"],
            "travel_date": fields["travel_date"],
        }

    def _extract(self, text: str, mode: str, follow_up: bool) -> dict[str, Any]:
        result: dict[str, Any] = {}
        travel_date = self._extract_date(text)
        if travel_date:
            result["travel_date"] = travel_date
        travel_time = self._extract_time(text)
        if travel_time:
            result["travel_time"] = travel_time
        seats = self._extract_seats(text)
        if seats:
            result["seats"] = seats
        fare = self._extract_fare(text)
        if fare is not None:
            result["fare"] = fare
        route = self._extract_route(text)
        if route:
            result["origin"], result["destination"] = route
        elif follow_up:
            # For pending flows, a short plain-place reply can fill whichever route field is missing.
            place = self._plain_place(text)
            if place:
                result["plain_place"] = place
        return result

    @staticmethod
    def _merge(base: dict[str, Any], new: dict[str, Any]) -> None:
        plain = new.pop("plain_place", None)
        for key, value in new.items():
            if value is not None:
                base[key] = value
        if plain:
            if not base.get("origin"):
                base["origin"] = plain
            elif not base.get("destination"):
                base["destination"] = plain

    @classmethod
    def _detect_mode(cls, text: str) -> str | None:
        lowered = text.casefold()
        if any(marker in lowered for marker in cls.DRIVER_MARKERS):
            return "DRIVER"
        if any(marker in lowered for marker in cls.PASSENGER_MARKERS):
            return "PASSENGER"
        # A route plus explicit seat inventory is a strong driver signal.
        if cls._extract_route(text) and cls._extract_seats(text) and any(w in lowered for w in ("ఉన్నాయి", "available", "empty", "खाली")):
            return "DRIVER"
        return None

    @classmethod
    def _extract_route(cls, text: str) -> tuple[str, str] | None:
        cleaned = cls._strip_schedule_and_inventory(text)
        patterns = (
            r"(?i)\bfrom\s+(.+?)\s+to\s+(.+?)(?=$|[,.;]|\s+(?:ride|car|driving|going|travelling|traveling|with))",
            r"(.+?)\s+నుంచి\s+(.+?)(?=$|[,.;]|\s+(?:వెళ|వెళ్ళ|వెళ్ల|ride|car|లో|కి|కు))",
            r"(.+?)\s+నుండి\s+(.+?)(?=$|[,.;]|\s+(?:వెళ|వెళ్ళ|వెళ్ల|ride|car|లో|కి|కు))",
            r"(.+?)\s+से\s+(.+?)(?=$|[,.;]|\s+(?:तक|जाना|जा|ride|car|के लिए))",
        )
        for pattern in patterns:
            match = re.search(pattern, cleaned)
            if not match:
                continue
            origin = cls._clean_place(match.group(1))
            destination = cls._clean_place(match.group(2))
            if origin and destination and origin.casefold() != destination.casefold():
                return origin, destination
        return None

    @staticmethod
    def _extract_date(text: str) -> str | None:
        lowered = text.casefold()
        if any(word in lowered for word in ("tomorrow", "రేపు", "कल")):
            return "Tomorrow"
        if any(word in lowered for word in ("today", "ఈరోజు", "ఇవాళ", "आज")):
            return "Today"
        match = re.search(r"\b\d{1,2}[-/]\d{1,2}(?:[-/]\d{2,4})?\b", text)
        return match.group(0) if match else None

    @staticmethod
    def _extract_time(text: str) -> str | None:
        direct = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text, flags=re.I)
        if direct:
            hour, minute, ap = direct.group(1), direct.group(2), direct.group(3).upper()
            return f"{hour}:{minute} {ap}" if minute else f"{hour} {ap}"
        markers = (
            (r"(?:ఉదయం|morning|सुबह)\s*(\d{1,2})(?::(\d{2}))?", "AM"),
            (r"(?:సాయంత్రం|evening|शाम)\s*(\d{1,2})(?::(\d{2}))?", "PM"),
            (r"(?:రాత్రి|night|रात)\s*(\d{1,2})(?::(\d{2}))?", "PM"),
        )
        for pattern, ap in markers:
            match = re.search(pattern, text, flags=re.I)
            if match:
                return f"{match.group(1)}:{match.group(2)} {ap}" if match.group(2) else f"{match.group(1)} {ap}"
        return None

    @staticmethod
    def _extract_seats(text: str) -> int | None:
        patterns = (
            r"\b(\d{1,2})\s*(?:seats?|seat)\b",
            r"\b(\d{1,2})\s*(?:సీట్లు|సీట్స్)\b",
            r"\b(\d{1,2})\s*(?:सीट|सीटें)\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                value = int(match.group(1))
                return value if 1 <= value <= 20 else None
        return None

    @staticmethod
    def _extract_fare(text: str) -> float | None:
        match = re.search(r"₹\s*(\d+(?:\.\d+)?)", text)
        if not match:
            match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:rs|rupees)\s*(?:/\s*seat|per\s*seat)?", text, flags=re.I)
        return float(match.group(1)) if match else None

    @classmethod
    def _strip_schedule_and_inventory(cls, text: str) -> str:
        value = str(text)
        value = re.sub(r"\b(?:today|tomorrow)\b|(?:ఈరోజు|ఇవాళ|రేపు|आज|कल)", " ", value, flags=re.I)
        value = re.sub(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", " ", value, flags=re.I)
        value = re.sub(r"(?:ఉదయం|సాయంత్రం|రాత్రి|morning|evening|night|सुबह|शाम|रात)\s*\d{1,2}(?::\d{2})?", " ", value, flags=re.I)
        value = re.sub(r"\b\d{1,2}\s*(?:seats?|సీట్లు|సీట్స్|सीट|सीटें)\b", " ", value, flags=re.I)
        value = re.sub(r"₹\s*\d+(?:\.\d+)?", " ", value)
        return " ".join(value.split())

    @staticmethod
    def _clean_place(value: str) -> str:
        value = re.sub(r"(?i)\b(?:i|am|i'm|నేను|मैं)\b", " ", str(value))
        value = re.sub(r"(?:వెళ్తున్నాను|వెళ్తున్నా|వెళ్లుతున్నాను|వెళ్ళుతున్నాను|కావాలి|చాహिए|चाहिए)$", " ", value, flags=re.I)
        return " ".join(value.strip(" ,.-").split())

    @classmethod
    def _plain_place(cls, text: str) -> str | None:
        if cls._extract_date(text) or cls._extract_time(text) or cls._extract_seats(text) or cls._extract_fare(text) is not None:
            return None
        value = cls._clean_place(text)
        if 1 <= len(value.split()) <= 4 and not any(ch.isdigit() for ch in value):
            return value
        return None

    @staticmethod
    def _prompt(mode: str, missing: str, fields: dict[str, Any]) -> str:
        if missing == "origin":
            return "🚗 Ride start place చెప్పండి. ఉదా: Vijayawada / విజయవాడ."
        if missing == "destination":
            return "📍 ఎక్కడికి వెళ్లాలి? Destination పేరు చెప్పండి. ఉదా: Hyderabad / హైదరాబాద్."
        if missing == "travel_date":
            return "📅 ఏ రోజు ride? Today / Tomorrow / date చెప్పండి."
        if missing == "travel_time":
            return "⏰ ఏ సమయానికి బయలుదేరుతారు? ఉదా: 8 AM లేదా సాయంత్రం 5."
        if missing == "seats":
            return "💺 ఎన్ని empty seats ఉన్నాయి? ఉదా: 3 seats."
        return "Ride detail చెప్పండి."

    def _get(self, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM ride_natural_intake WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    def _save(self, user_id: str, mode: str, fields: dict[str, Any]) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ride_natural_intake(user_id,mode,origin,destination,travel_date,travel_time,seats,fare,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET
                    mode=excluded.mode, origin=excluded.origin, destination=excluded.destination,
                    travel_date=excluded.travel_date, travel_time=excluded.travel_time,
                    seats=excluded.seats, fare=excluded.fare, updated_at=excluded.updated_at
                """,
                (user_id, mode, fields.get("origin"), fields.get("destination"), fields.get("travel_date"),
                 fields.get("travel_time"), fields.get("seats"), fields.get("fare"), now),
            )

    def _clear(self, user_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM ride_natural_intake WHERE user_id=?", (user_id,))
