from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Sequence
from uuid import uuid4


class RevenueRouteType(str, Enum):
    """How PODX can route a genuine user requirement."""

    LOCAL_MATCH = "local_match"
    AFFILIATE_REDIRECT = "affiliate_redirect"
    PARTNER_LEAD = "partner_lead"


class OfferChannel(str, Enum):
    LOCAL = "local"
    ONLINE = "online"
    PARTNER = "partner"


class ConversionStatus(str, Enum):
    OPEN = "open"
    CLICKED = "clicked"
    LEAD_SENT = "lead_sent"
    CONVERTED = "converted"
    CLOSED_NO_CONVERSION = "closed_no_conversion"


@dataclass(frozen=True)
class UserRequirement:
    user_id: str
    intent: str
    category: str
    explicit_requirement: bool
    consent_to_partner_handoff: bool = False
    attributes: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RevenueOffer:
    """A candidate route. Commercial payout data must never drive ranking."""

    offer_id: str
    partner_id: str
    category: str
    route_type: RevenueRouteType
    channel: OfferChannel
    suitability_score: float
    trust_score: float
    convenience_score: float = 0.0
    destination_url: str | None = None
    enabled: bool = True
    requires_consent: bool = False
    regulated_handoff: bool = False
    disclosure: str | None = None
    commercial_metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RevenueDecision:
    requirement: UserRequirement
    selected_offer: RevenueOffer | None
    ranked_offers: tuple[RevenueOffer, ...]
    monetization_allowed: bool
    reason: str


@dataclass(frozen=True)
class RevenueAttribution:
    attribution_id: str
    user_id: str
    intent: str
    category: str
    partner_id: str
    offer_id: str
    route_type: RevenueRouteType
    status: ConversionStatus = ConversionStatus.OPEN
    click_id: str | None = None
    lead_id: str | None = None
    conversion_id: str | None = None


class UniversalRevenueRouterService:
    """Trust-first router for local, online affiliate and partner-lead options.

    Permanent policy:
    - No commercial route without a genuine user requirement.
    - Partner handoff requiring consent is blocked until consent exists.
    - Commission/payout metadata is never used to rank offers.
    - Local and online routes compete on user-fit signals, not PODX revenue.
    - Regulated products are handoff routes only; the partner closes the deal.
    """

    @staticmethod
    def _score(offer: RevenueOffer) -> tuple[float, float, float, str]:
        return (
            float(offer.suitability_score),
            float(offer.trust_score),
            float(offer.convenience_score),
            offer.offer_id,
        )

    def rank_offers(
        self,
        requirement: UserRequirement,
        offers: Iterable[RevenueOffer],
    ) -> tuple[RevenueOffer, ...]:
        eligible = [
            offer
            for offer in offers
            if offer.enabled
            and offer.category.strip().casefold() == requirement.category.strip().casefold()
            and (not offer.requires_consent or requirement.consent_to_partner_handoff)
        ]
        return tuple(sorted(eligible, key=self._score, reverse=True))

    def decide(
        self,
        requirement: UserRequirement,
        offers: Sequence[RevenueOffer],
    ) -> RevenueDecision:
        if not requirement.explicit_requirement:
            return RevenueDecision(
                requirement=requirement,
                selected_offer=None,
                ranked_offers=(),
                monetization_allowed=False,
                reason="No explicit user requirement; do not activate a commercial route.",
            )

        ranked = self.rank_offers(requirement, offers)
        if not ranked:
            return RevenueDecision(
                requirement=requirement,
                selected_offer=None,
                ranked_offers=(),
                monetization_allowed=False,
                reason="No eligible route matches the requirement and consent state.",
            )

        return RevenueDecision(
            requirement=requirement,
            selected_offer=ranked[0],
            ranked_offers=ranked,
            monetization_allowed=True,
            reason="Selected on user fit and trust signals; commercial payout was not ranked.",
        )

    @staticmethod
    def create_attribution(
        requirement: UserRequirement,
        offer: RevenueOffer,
    ) -> RevenueAttribution:
        return RevenueAttribution(
            attribution_id=f"podx_{uuid4().hex}",
            user_id=requirement.user_id,
            intent=requirement.intent,
            category=requirement.category,
            partner_id=offer.partner_id,
            offer_id=offer.offer_id,
            route_type=offer.route_type,
        )
