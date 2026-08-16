"""Route-stop sequencing and pickup/drop matching for PODX rides."""
from __future__ import annotations

import math
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.services.google_maps_service import GoogleMapsService


class RideRouteService:
    def __init__(self, ride_repository, user_repository=None, maps_service=None) -> None:
        self.rides = ride_repository
        self.db_path = getattr(ride_repository, "db_path", "podx.db")
        self.users = user_repository
        self.maps = maps_service or GoogleMapsService()
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
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ride_route_points(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ride_id INTEGER NOT NULL,
                    sequence_no INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    kind TEXT NOT NULL DEFAULT 'STOP',
                    created_at TEXT NOT NULL,
                    UNIQUE(ride_id, sequence_no)
                );
                CREATE INDEX IF NOT EXISTS idx_ride_route_points_ride
                ON ride_route_points(ride_id, sequence_no);

                CREATE TABLE IF NOT EXISTS ride_search_context(
                    passenger_user_id TEXT PRIMARY KEY,
                    ride_id INTEGER NOT NULL,
                    pickup_name TEXT NOT NULL,
                    drop_name TEXT NOT NULL,
                    pickup_sequence INTEGER NOT NULL,
                    drop_sequence INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def initialize_route(self, ride_id: int, origin: str, destination: str, driver_user_id: str | None = None) -> None:
        origin_point = self._parse_point(origin)
        destination_point = self._parse_point(destination)
        if driver_user_id and self.users is not None and not self._has_coordinates(origin_point):
            user = self.users.find_by_whatsapp_mobile(str(driver_user_id)) or {}
            saved_name = self._norm(user.get("location_name") or user.get("area"))
            if saved_name and self._place_match(saved_name, self._norm(origin)):
                try:
                    origin_point["latitude"] = float(user.get("latitude"))
                    origin_point["longitude"] = float(user.get("longitude"))
                except (TypeError, ValueError):
                    origin_point.pop("latitude", None)
                    origin_point.pop("longitude", None)
        origin_point = self._enrich_point(origin_point)
        destination_point = self._enrich_point(destination_point)
        with self._connect() as conn:
            existing = conn.execute("SELECT 1 FROM ride_route_points WHERE ride_id=? LIMIT 1", (int(ride_id),)).fetchone()
            if existing:
                return
            now = self._now()
            conn.execute("INSERT INTO ride_route_points(ride_id,sequence_no,name,latitude,longitude,kind,created_at) VALUES(?,?,?,?,?,'ORIGIN',?)", (int(ride_id), 0, origin_point["name"], origin_point.get("latitude"), origin_point.get("longitude"), now))
            conn.execute("INSERT INTO ride_route_points(ride_id,sequence_no,name,latitude,longitude,kind,created_at) VALUES(?,?,?,?,?,'DESTINATION',?)", (int(ride_id), 1, destination_point["name"], destination_point.get("latitude"), destination_point.get("longitude"), now))

    def set_stops(self, ride_id: int, driver_user_id: str, stop_specs: list[str]) -> dict[str, Any]:
        ride = self.rides.get_ride(int(ride_id))
        if not ride:
            return {"status": "NOT_FOUND"}
        if str(ride.get("driver_user_id")) != str(driver_user_id):
            return {"status": "NOT_DRIVER"}
        parsed = [self._enrich_point(self._parse_point(x)) for x in stop_specs if str(x).strip()]
        parsed = [p for p in parsed if p.get("name")]
        now = self._now()
        with self._connect() as conn:
            conn.execute("DELETE FROM ride_route_points WHERE ride_id=?", (int(ride_id),))
            origin = self._enrich_point(self._parse_point(str(ride["origin"])))
            destination = self._enrich_point(self._parse_point(str(ride["destination"])))
            points = [(origin, "ORIGIN"), *[(p, "STOP") for p in parsed], (destination, "DESTINATION")]
            for idx, (point, kind) in enumerate(points):
                conn.execute(
                    "INSERT INTO ride_route_points(ride_id,sequence_no,name,latitude,longitude,kind,created_at) VALUES(?,?,?,?,?,?,?)",
                    (int(ride_id), idx, point["name"], point.get("latitude"), point.get("longitude"), kind, now),
                )
        return {"status": "SAVED", "points": self.get_points(ride_id), "overview": self.route_overview(ride_id)}

    def get_points(self, ride_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM ride_route_points WHERE ride_id=? ORDER BY sequence_no", (int(ride_id),)).fetchall()
        return [dict(r) for r in rows]

    def route_overview(self, ride_id: int) -> dict[str, Any] | None:
        ride = self.rides.get_ride(int(ride_id))
        if not ride:
            return None
        points = self.get_points(int(ride_id))
        if not points:
            self.initialize_route(int(ride_id), str(ride["origin"]), str(ride["destination"]), str(ride["driver_user_id"]))
            points = self.get_points(int(ride_id))
        names = [str(point.get("name") or "").strip() for point in points if str(point.get("name") or "").strip()]
        if len(names) < 2:
            return None
        directions_url = self.maps.directions_url(names[0], names[-1], names[1:-1])
        route = self.maps.compute_route(points)
        overview: dict[str, Any] = {
            "ride_id": int(ride_id),
            "origin": names[0],
            "destination": names[-1],
            "waypoints": names[1:-1],
            "directions_url": directions_url,
            "maps_enabled": bool(getattr(self.maps, "enabled", False)),
        }
        if route:
            overview.update(route)
        return overview

    def find_subroute(self, passenger_user_id: str, origin: str, destination: str, travel_date: str, limit: int = 8) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rides = conn.execute("SELECT * FROM rides WHERE status='OPEN' AND seats_available>0 ORDER BY id DESC LIMIT 200").fetchall()
        passenger = self.users.find_by_whatsapp_mobile(str(passenger_user_id)) if self.users is not None else None
        plat = (passenger or {}).get("latitude")
        plon = (passenger or {}).get("longitude")
        out: list[dict[str, Any]] = []
        for row in rides:
            ride = dict(row)
            if self._norm(travel_date) and self._norm(ride.get("travel_date")) != self._norm(travel_date):
                continue
            points = self.get_points(int(ride["id"]))
            if not points:
                self.initialize_route(int(ride["id"]), str(ride["origin"]), str(ride["destination"]), str(ride["driver_user_id"]))
                points = self.get_points(int(ride["id"]))
            pickup_candidates = [p for p in points if self._place_match(self._norm(origin), self._norm(p.get("name")))]
            drop_candidates = [p for p in points if self._place_match(self._norm(destination), self._norm(p.get("name")))]
            pairs = [(a, b) for a in pickup_candidates for b in drop_candidates if int(a["sequence_no"]) < int(b["sequence_no"])]
            if not pairs:
                continue
            pickup, drop = min(pairs, key=lambda pair: self._pickup_distance(pair[0], plat, plon))
            distance = self._pickup_distance(pickup, plat, plon)
            out.append({**ride, "pickup_name": pickup["name"], "drop_name": drop["name"], "pickup_sequence": pickup["sequence_no"], "drop_sequence": drop["sequence_no"], "pickup_distance_km": None if distance >= 999999 else round(distance, 2), "directions_url": self.maps.directions_url(str(pickup["name"]), str(drop["name"]))})
        out.sort(key=lambda x: (x.get("pickup_distance_km") is None, x.get("pickup_distance_km") or 0, -int(x["id"])))
        selected = out[: max(1, int(limit))]
        if selected:
            best = selected[0]
            self.save_search_context(passenger_user_id, best)
        return selected

    def save_search_context(self, passenger_user_id: str, match: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO ride_search_context(passenger_user_id,ride_id,pickup_name,drop_name,pickup_sequence,drop_sequence,updated_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(passenger_user_id) DO UPDATE SET ride_id=excluded.ride_id,pickup_name=excluded.pickup_name,drop_name=excluded.drop_name,pickup_sequence=excluded.pickup_sequence,drop_sequence=excluded.drop_sequence,updated_at=excluded.updated_at""",
                (str(passenger_user_id), int(match["id"]), str(match["pickup_name"]), str(match["drop_name"]), int(match["pickup_sequence"]), int(match["drop_sequence"]), self._now()),
            )

    def context_for_booking(self, passenger_user_id: str, ride_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM ride_search_context WHERE passenger_user_id=? AND ride_id=?", (str(passenger_user_id), int(ride_id))).fetchone()
        return dict(row) if row else None

    def _enrich_point(self, point: dict[str, Any]) -> dict[str, Any]:
        if self._has_coordinates(point) or not str(point.get("name") or "").strip():
            return point
        geocoded = self.maps.geocode(str(point["name"]))
        if not geocoded:
            return point
        return {**point, "latitude": geocoded.get("latitude"), "longitude": geocoded.get("longitude")}

    @staticmethod
    def _has_coordinates(point: dict[str, Any]) -> bool:
        try:
            float(point["latitude"])
            float(point["longitude"])
            return True
        except (KeyError, TypeError, ValueError):
            return False

    @staticmethod
    def _parse_point(spec: str) -> dict[str, Any]:
        text = str(spec or "").strip()
        m = re.match(r"^(.*?)\s*@\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$", text)
        if not m:
            return {"name": text}
        return {"name": m.group(1).strip(), "latitude": float(m.group(2)), "longitude": float(m.group(3))}

    @staticmethod
    def _norm(value: Any) -> str:
        return " ".join(str(value or "").casefold().strip().split())

    @classmethod
    def _place_match(cls, a: str, b: str) -> bool:
        return bool(a and b and (a == b or a in b or b in a))

    @staticmethod
    def _pickup_distance(point: dict[str, Any], lat: Any, lon: Any) -> float:
        try:
            lat1, lon1 = float(lat), float(lon)
            lat2, lon2 = float(point["latitude"]), float(point["longitude"])
        except (TypeError, ValueError, KeyError):
            return 999999.0
        r = 6371.0088
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
        return r * 2 * math.atan2(math.sqrt(h), math.sqrt(max(0.0, 1 - h)))
