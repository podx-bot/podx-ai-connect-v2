"""Targeted expansion planner for unmatched universal NEED/OFFER records.

This module decides who should be contacted next when a direct match is absent.
It does not send WhatsApp messages itself; it returns a ranked, deduplicated plan
that the delivery layer can execute safely.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Iterable, List


@dataclass
class TargetCandidate:
    user_id: str
    score: float
    distance_km: float | None
    reason: str
    wave: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class UniversalTargetingService:
    """Build progressive nearby/relevant notification waves.

    Profile records are intentionally generic dictionaries so this service can be
    reused for sellers, workers, service providers, businesses and future roles.
    """

    DEFAULT_RADII_KM = (5.0, 15.0, 30.0, 50.0)
    GENERIC_PROFILE_WORDS = {
        "and", "or", "the", "a", "an", "shop", "store", "business", "seller",
        "provider", "service", "services", "worker", "workers", "product", "products",
    }

    def __init__(
        self,
        profile_source: Callable[[], Iterable[Dict[str, Any]]],
        subject_similarity: Callable[[Any, Any], float],
        distance_km: Callable[[Dict[str, Any], Dict[str, Any]], float | None],
        radii_km: tuple[float, ...] = DEFAULT_RADII_KM,
    ) -> None:
        self.profile_source = profile_source
        self.subject_similarity = subject_similarity
        self.distance_km = distance_km
        self.radii_km = tuple(float(r) for r in radii_km)

    def build_plan(
        self,
        request: Dict[str, Any],
        already_contacted_user_ids: Iterable[str] | None = None,
        per_wave_limit: int = 25,
    ) -> Dict[str, Any]:
        excluded = {str(x) for x in (already_contacted_user_ids or [])}
        requester = str(request.get("user_id") or "")
        if requester:
            excluded.add(requester)

        profiles = list(self.profile_source())
        candidates: List[Dict[str, Any]] = []
        for profile in profiles:
            user_id = str(profile.get("user_id") or profile.get("phone") or "")
            if not user_id or user_id in excluded:
                continue
            if not self._role_compatible(request, profile):
                continue

            relevance = self._profile_relevance(request, profile)
            if relevance < 0.35:
                continue
            distance = self.distance_km(request, profile)
            candidates.append(
                {
                    "user_id": user_id,
                    "relevance": relevance,
                    "distance_km": distance,
                }
            )

        waves: List[Dict[str, Any]] = []
        selected: set[str] = set()
        for wave_index, radius in enumerate(self.radii_km, start=1):
            wave_items: List[TargetCandidate] = []
            for candidate in candidates:
                if candidate["user_id"] in selected:
                    continue
                distance = candidate["distance_km"]
                if distance is not None and distance > radius:
                    continue
                distance_score = self._distance_score(distance, radius)
                score = candidate["relevance"] * 0.72 + distance_score * 0.28
                wave_items.append(
                    TargetCandidate(
                        user_id=candidate["user_id"],
                        score=round(score, 4),
                        distance_km=round(distance, 2) if distance is not None else None,
                        reason="relevant_profile_nearby" if distance is not None else "relevant_profile_location_unknown",
                        wave=wave_index,
                    )
                )

            wave_items.sort(key=lambda item: item.score, reverse=True)
            wave_items = wave_items[: max(1, int(per_wave_limit))]
            selected.update(item.user_id for item in wave_items)
            if wave_items:
                waves.append(
                    {
                        "wave": wave_index,
                        "radius_km": radius,
                        "targets": [item.to_dict() for item in wave_items],
                    }
                )

        return {
            "status": "TARGETED" if waves else "HOLD",
            "request_id": request.get("id"),
            "subject": request.get("subject"),
            "total_targets": sum(len(w["targets"]) for w in waves),
            "waves": waves,
        }

    def _profile_relevance(self, request: Dict[str, Any], profile: Dict[str, Any]) -> float:
        request_subject = request.get("subject")
        texts = [
            profile.get("subject"),
            profile.get("category"),
            profile.get("business_type"),
            profile.get("skill"),
            profile.get("service"),
        ]
        products = profile.get("products") or []
        if isinstance(products, str):
            products = [products]
        texts.extend(products)

        best = 0.0
        request_tokens = self._meaningful_tokens(request_subject)
        for text in texts:
            if not text:
                continue
            semantic_score = float(self.subject_similarity(request_subject, text) or 0.0)
            profile_tokens = self._meaningful_tokens(text)
            shared = request_tokens & profile_tokens

            # A profile may be relevant even when it has not listed the exact item.
            # Example: "sona masoori rice" should reach a registered "rice grocery"
            # seller because the concrete shared business term is "rice".
            token_score = 0.0
            if shared:
                coverage = len(shared) / max(1, min(len(request_tokens), len(profile_tokens)))
                token_score = min(0.75, 0.42 + (0.25 * coverage))

            best = max(best, semantic_score, token_score)
        return best

    @classmethod
    def _meaningful_tokens(cls, value: Any) -> set[str]:
        text = str(value or "").casefold()
        tokens = set(re.findall(r"[\w]+", text, flags=re.UNICODE))
        return {token for token in tokens if len(token) >= 2 and token not in cls.GENERIC_PROFILE_WORDS}

    @staticmethod
    def _role_compatible(request: Dict[str, Any], profile: Dict[str, Any]) -> bool:
        domain = str(request.get("domain") or "OTHER").upper()
        side = str(request.get("side") or "NEED").upper()
        role = str(profile.get("role") or profile.get("profile_type") or "").upper()

        if domain == "PRODUCT":
            return role in {"SELLER", "BUSINESS", "BOTH", "PROVIDER", ""} if side == "NEED" else role in {"BUYER", "BOTH", ""}
        if domain == "SERVICE":
            return role in {"SERVICE_PROVIDER", "PROVIDER", "BUSINESS", "BOTH", ""} if side == "NEED" else role in {"CUSTOMER", "BUYER", "BOTH", ""}
        if domain == "WORK":
            return role in {"EMPLOYER", "JOB_PROVIDER", "BUSINESS", "BOTH", ""}
        if domain == "WORKERS":
            return role in {"WORKER", "JOB_SEEKER", "BOTH", ""}
        return True

    @staticmethod
    def _distance_score(distance_km: float | None, radius_km: float) -> float:
        if distance_km is None:
            return 0.35
        if distance_km <= 0:
            return 1.0
        return max(0.1, 1.0 - min(distance_km / max(radius_km, 0.1), 1.0) * 0.7)
