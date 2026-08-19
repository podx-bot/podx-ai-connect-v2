from urllib.parse import parse_qs, urlsplit

from app.services.deep_link_resolver_service import DeepLinkResolverService
from app.services.partner_registry_service import (
    PartnerDefinition,
    PartnerRegistryService,
    PartnerStatus,
)
from app.services.universal_revenue_router_service import OfferChannel, RevenueRouteType


def _partner(**overrides):
    values = {
        "partner_id": "merchant_a",
        "display_name": "Merchant A",
        "categories": ("products",),
        "route_type": RevenueRouteType.AFFILIATE_REDIRECT,
        "channel": OfferChannel.ONLINE,
        "base_url": "https://example.com/item?existing=1",
        "tracking_parameter": "tag",
        "tracking_value": "podx-21",
    }
    values.update(overrides)
    return PartnerDefinition(**values)


def test_registry_filters_disabled_and_wrong_category_partners():
    registry = PartnerRegistryService(
        [
            _partner(),
            _partner(partner_id="paused", status=PartnerStatus.PAUSED),
            _partner(partner_id="insurance", categories=("insurance",)),
        ]
    )

    active = registry.active_for_category("PRODUCTS")

    assert [partner.partner_id for partner in active] == ["merchant_a"]


def test_registry_keeps_commercial_terms_as_metadata_only():
    partner = _partner(commercial_metadata={"commission_percent": 20})
    registry = PartnerRegistryService([partner])

    stored = registry.get("merchant_a")

    assert stored is not None
    assert stored.commercial_metadata["commission_percent"] == 20


def test_deep_link_resolver_preserves_existing_query_and_adds_tracking():
    partner = _partner()
    resolved = DeepLinkResolverService().resolve(
        partner,
        attribution_id="podx_abc123",
    )

    assert resolved is not None
    query = parse_qs(urlsplit(resolved.url).query)
    assert query["existing"] == ["1"]
    assert query["tag"] == ["podx-21"]
    assert query["podx_attribution_id"] == ["podx_abc123"]


def test_deep_link_resolver_can_use_offer_specific_destination():
    partner = _partner(base_url="https://example.com")
    resolved = DeepLinkResolverService().resolve(
        partner,
        attribution_id="podx_xyz",
        destination_url="https://example.com/product/42",
    )

    assert resolved is not None
    assert urlsplit(resolved.url).path == "/product/42"


def test_deep_link_resolver_returns_none_when_no_destination_exists():
    partner = _partner(base_url=None)

    assert (
        DeepLinkResolverService().resolve(partner, attribution_id="podx_missing")
        is None
    )
