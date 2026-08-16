"""Small, failure-tolerant Google Maps Platform client for PODX server-side use."""
from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import quote_plus

import httpx


class GoogleMapsService:
    GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
    ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

    def __init__(self, api_key: str | None = None, timeout_seconds: float | None = None, client=None) -> None:
        self.api_key = str(api_key if api_key is not None else os.getenv("GOOGLE_MAPS_API_KEY", "")).strip()
        raw_timeout = timeout_seconds if timeout_seconds is not None else os.getenv("GOOGLE_MAPS_TIMEOUT_SECONDS", "5")
        try:
            self.timeout_seconds = max(1.0, float(raw_timeout))
        except (TypeError, ValueError):
            self.timeout_seconds = 5.0
        self.client = client or httpx.Client(timeout=self.timeout_seconds)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def geocode(self, place: str, region: str = "in") -> dict[str, Any] | None:
        query = " ".join(str(place or "").strip().split())
        if not self.enabled or not query:
            return None
        try:
            response = self.client.get(
                self.GEOCODE_URL,
                params={"address": query, "region": region, "key": self.api_key},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            return None
        if str(payload.get("status") or "").upper() != "OK":
            return None
        results = payload.get("results") or []
        if not results:
            return None
        first = results[0] or {}
        location = ((first.get("geometry") or {}).get("location") or {})
        try:
            lat, lon = float(location["lat"]), float(location["lng"])
        except (KeyError, TypeError, ValueError):
            return None
        return {
            "name": str(first.get("formatted_address") or query),
            "latitude": lat,
            "longitude": lon,
            "place_id": str(first.get("place_id") or ""),
        }

    def compute_route(self, points: list[dict[str, Any]]) -> dict[str, Any] | None:
        coords = [self._lat_lng(point) for point in points]
        coords = [point for point in coords if point is not None]
        if not self.enabled or len(coords) < 2:
            return None
        body: dict[str, Any] = {
            "origin": {"location": {"latLng": coords[0]}},
            "destination": {"location": {"latLng": coords[-1]}},
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE",
        }
        if len(coords) > 2:
            body["intermediates"] = [{"location": {"latLng": point}} for point in coords[1:-1]]
        headers = {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline",
            "Content-Type": "application/json",
        }
        try:
            response = self.client.post(self.ROUTES_URL, json=body, headers=headers, timeout=self.timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            return None
        routes = payload.get("routes") or []
        if not routes:
            return None
        route = routes[0] or {}
        try:
            distance_m = int(route.get("distanceMeters") or 0)
        except (TypeError, ValueError):
            distance_m = 0
        duration_s = self._duration_seconds(route.get("duration"))
        polyline = ((route.get("polyline") or {}).get("encodedPolyline") or "")
        return {
            "distance_meters": distance_m,
            "distance_km": round(distance_m / 1000.0, 2) if distance_m else None,
            "duration_seconds": duration_s,
            "duration_minutes": round(duration_s / 60) if duration_s is not None else None,
            "encoded_polyline": str(polyline),
        }

    @staticmethod
    def directions_url(origin: str, destination: str, waypoints: list[str] | None = None) -> str:
        params = [
            "api=1",
            f"origin={quote_plus(str(origin or '').strip())}",
            f"destination={quote_plus(str(destination or '').strip())}",
            "travelmode=driving",
        ]
        clean_waypoints = [str(x).strip() for x in (waypoints or []) if str(x).strip()]
        if clean_waypoints:
            params.append("waypoints=" + quote_plus("|".join(clean_waypoints)))
        return "https://www.google.com/maps/dir/?" + "&".join(params)

    @staticmethod
    def _lat_lng(point: dict[str, Any]) -> dict[str, float] | None:
        try:
            return {"latitude": float(point["latitude"]), "longitude": float(point["longitude"])}
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _duration_seconds(value: Any) -> int | None:
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)s\s*", str(value or ""))
        return int(round(float(match.group(1)))) if match else None
