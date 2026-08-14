"""Universal Party A ↔ Party B matching for PODX.

The matcher is intentionally category-light. It ranks compatible active records
using relationship compatibility, free-form subject similarity, distance, time,
quantity and price. Unknown future subjects can still match without adding code.
"""

from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List


class UniversalMatcher:
    DEFAULT_MIN_SCORE = 0.48

    def __init__(self, repository, min_score: float = DEFAULT_MIN_SCORE) -> None:
        self.repository = repository
        self.min_score = float(min_score)

    def find_matches(self, record: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
        candidates = self.repository.list_active(
            limit=500,
            exclude_user_id=str(record.get("user_id") or ""),
        )
        ranked: List[Dict[str, Any]] = []
        for candidate in candidates:
            if record.get("id") and candidate.get("id") == record.get("id"):
                continue
            if not self._relationship_compatible(record, candidate):
                continue
            scored = self.score(record, candidate)
            if scored["score"] >= self.min_score:
                ranked.append({**candidate, **scored})
        ranked.sort(key=lambda item: (item["score"], -(item.get("distance_km") or 0.0)), reverse=True)
        return ranked[: max(1, int(limit))]

    def score(self, a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        subject = self._subject_similarity(a.get("subject"), b.get("subject"))
        distance_km = self._distance_km(a, b)
        distance = self._distance_score(distance_km)
        time_score = self._time_score(a.get("when_text") or a.get("when"), b.get("when_text") or b.get("when"))
        quantity = self._quantity_score(a, b)
        price = self._price_score(a, b)

        # Subject is the strongest signal. Location is next because PODX is local-first.
        score = (
            subject * 0.46
            + distance * 0.24
            + time_score * 0.12
            + quantity * 0.09
            + price * 0.09
        )
        return {
            "score": round(score, 4),
            "subject_score": round(subject, 4),
            "distance_score": round(distance, 4),
            "distance_km": round(distance_km, 2) if distance_km is not None else None,
            "time_score": round(time_score, 4),
            "quantity_score": round(quantity, 4),
            "price_score": round(price, 4),
        }

    @staticmethod
    def _relationship_compatible(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
        da = str(a.get("domain") or "OTHER").upper()
        db = str(b.get("domain") or "OTHER").upper()
        sa = str(a.get("side") or "NEED").upper()
        sb = str(b.get("side") or "NEED").upper()

        # Worker looking for work ↔ employer looking for workers is a fulfilment
        # relationship even though natural-language extraction may mark both as NEED.
        if {da, db} == {"WORK", "WORKERS"}:
            return True

        # Products/services/other offers fulfil needs in the same broad domain.
        if da == db:
            return sa != sb
        return False

    @classmethod
    def _subject_similarity(cls, left: Any, right: Any) -> float:
        a = cls._normalize_text(left)
        b = cls._normalize_text(right)
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        ta, tb = set(a.split()), set(b.split())
        union = ta | tb
        jaccard = len(ta & tb) / len(union) if union else 0.0
        sequence = SequenceMatcher(None, a, b).ratio()
        containment = 1.0 if a in b or b in a else 0.0
        return max(jaccard, sequence * 0.85, containment * 0.92)

    @staticmethod
    def _normalize_text(value: Any) -> str:
        text = str(value or "").casefold().strip()
        text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
        return " ".join(text.split())

    @staticmethod
    def _distance_km(a: Dict[str, Any], b: Dict[str, Any]) -> float | None:
        try:
            lat1, lon1 = float(a["latitude"]), float(a["longitude"])
            lat2, lon2 = float(b["latitude"]), float(b["longitude"])
        except (KeyError, TypeError, ValueError):
            return None
        radius = 6371.0088
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
        return radius * 2 * math.atan2(math.sqrt(h), math.sqrt(max(0.0, 1 - h)))

    @staticmethod
    def _distance_score(distance_km: float | None) -> float:
        if distance_km is None:
            return 0.5
        if distance_km <= 2:
            return 1.0
        if distance_km <= 5:
            return 0.9
        if distance_km <= 10:
            return 0.75
        if distance_km <= 25:
            return 0.5
        if distance_km <= 50:
            return 0.25
        return 0.05

    @classmethod
    def _time_score(cls, left: Any, right: Any) -> float:
        if not left or not right:
            return 0.7
        a, b = cls._normalize_text(left), cls._normalize_text(right)
        if a == b or a in b or b in a:
            return 1.0
        today_terms = ("today", "ఈరోజు", "ఈ రోజు")
        tomorrow_terms = ("tomorrow", "రేపు")
        if cls._contains_any(a, today_terms) and cls._contains_any(b, today_terms):
            return 1.0
        if cls._contains_any(a, tomorrow_terms) and cls._contains_any(b, tomorrow_terms):
            return 1.0
        if (cls._contains_any(a, today_terms) and cls._contains_any(b, tomorrow_terms)) or (
            cls._contains_any(a, tomorrow_terms) and cls._contains_any(b, today_terms)
        ):
            return 0.15
        return 0.6

    @staticmethod
    def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
        return any(term in text for term in terms)

    @staticmethod
    def _quantity_score(a: Dict[str, Any], b: Dict[str, Any]) -> float:
        qa, qb = a.get("quantity"), b.get("quantity")
        if qa is None or qb is None:
            return 0.75
        try:
            qa, qb = float(qa), float(qb)
        except (TypeError, ValueError):
            return 0.75
        need, offer = (a, b) if str(a.get("side")).upper() == "NEED" else (b, a)
        q_need = need.get("quantity")
        q_offer = offer.get("quantity")
        if q_need is not None and q_offer is not None:
            try:
                return 1.0 if float(q_offer) >= float(q_need) else max(0.2, float(q_offer) / max(float(q_need), 1e-9))
            except (TypeError, ValueError):
                pass
        ratio = min(qa, qb) / max(qa, qb, 1e-9)
        return max(0.2, ratio)

    @staticmethod
    def _price_score(a: Dict[str, Any], b: Dict[str, Any]) -> float:
        pa, pb = a.get("price"), b.get("price")
        if pa is None or pb is None:
            return 0.75
        try:
            pa, pb = float(pa), float(pb)
        except (TypeError, ValueError):
            return 0.75
        if str(a.get("side")).upper() == "NEED" and str(b.get("side")).upper() == "OFFER":
            return 1.0 if pb <= pa else max(0.1, pa / max(pb, 1e-9))
        if str(b.get("side")).upper() == "NEED" and str(a.get("side")).upper() == "OFFER":
            return 1.0 if pa <= pb else max(0.1, pb / max(pa, 1e-9))
        return max(0.2, min(pa, pb) / max(pa, pb, 1e-9))
