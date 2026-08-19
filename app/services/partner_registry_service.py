from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping

from app.services.universal_revenue_router_service import OfferChannel, RevenueRouteType


class PartnerStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


@dataclass(frozen=True)
class PartnerDefinition:
    """Configuration for a monetization or lead partner.

    Keep commercial terms as metadata only. They are intentionally excluded from
    user recommendation ranking.
    """

    partner_id: str
    display_name: str
    categories: tuple[str, ...]
    route_type: RevenueRouteType
    channel: OfferChannel
    status: PartnerStatus = PartnerStatus.ACTIVE
    base_url: str | None = None
    tracking_parameter: str | None = None
    tracking_value: str | None = None
    requires_consent: bool = False
    regulated_handoff: bool = False
    disclosure: str | None = None
    commercial_metadata: Mapping[str, object] = field(default_factory=dict)

    def supports(self, category: str) -> bool:
        wanted = category.strip().casefold()
        return any(item.strip().casefold() == wanted for item in self.categories)


class PartnerRegistryService:
    """Simple partner registry shared by affiliate, local, and lead routes."""

    def __init__(self, partners: Iterable[PartnerDefinition] = ()) -> None:
        self._partners: dict[str, PartnerDefinition] = {
            partner.partner_id: partner for partner in partners
        }

    def register(self, partner: PartnerDefinition) -> None:
        self._partners[partner.partner_id] = partner

    def get(self, partner_id: str) -> PartnerDefinition | None:
        return self._partners.get(partner_id)

    def active_for_category(self, category: str) -> tuple[PartnerDefinition, ...]:
        return tuple(
            partner
            for partner in self._partners.values()
            if partner.status is PartnerStatus.ACTIVE and partner.supports(category)
        )

    def all(self) -> tuple[PartnerDefinition, ...]:
        return tuple(self._partners.values())
