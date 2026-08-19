from app.services.universal_revenue_router_service import (
    ConversionStatus,
    OfferChannel,
    RevenueOffer,
    RevenueRouteType,
    UniversalRevenueRouterService,
    UserRequirement,
)


def _offer(
    offer_id: str,
    *,
    suitability: float,
    trust: float,
    channel: OfferChannel,
    route_type: RevenueRouteType,
    requires_consent: bool = False,
    commercial_metadata=None,
):
    return RevenueOffer(
        offer_id=offer_id,
        partner_id=f"partner-{offer_id}",
        category="air conditioner",
        route_type=route_type,
        channel=channel,
        suitability_score=suitability,
        trust_score=trust,
        convenience_score=0.5,
        requires_consent=requires_consent,
        commercial_metadata=commercial_metadata or {},
    )


def test_does_not_monetize_without_explicit_requirement():
    service = UniversalRevenueRouterService()
    requirement = UserRequirement(
        user_id="u1",
        intent="browse",
        category="air conditioner",
        explicit_requirement=False,
    )

    decision = service.decide(
        requirement,
        [
            _offer(
                "online",
                suitability=0.99,
                trust=0.99,
                channel=OfferChannel.ONLINE,
                route_type=RevenueRouteType.AFFILIATE_REDIRECT,
            )
        ],
    )

    assert decision.monetization_allowed is False
    assert decision.selected_offer is None


def test_commission_metadata_cannot_override_better_user_fit():
    service = UniversalRevenueRouterService()
    requirement = UserRequirement(
        user_id="u2",
        intent="buy",
        category="air conditioner",
        explicit_requirement=True,
    )

    high_commission_lower_fit = _offer(
        "high-commission",
        suitability=0.65,
        trust=0.70,
        channel=OfferChannel.ONLINE,
        route_type=RevenueRouteType.AFFILIATE_REDIRECT,
        commercial_metadata={"commission_percent": 25},
    )
    local_best_fit = _offer(
        "local-best",
        suitability=0.95,
        trust=0.92,
        channel=OfferChannel.LOCAL,
        route_type=RevenueRouteType.LOCAL_MATCH,
        commercial_metadata={"commission_percent": 0},
    )

    decision = service.decide(requirement, [high_commission_lower_fit, local_best_fit])

    assert decision.selected_offer.offer_id == "local-best"
    assert [offer.offer_id for offer in decision.ranked_offers] == [
        "local-best",
        "high-commission",
    ]


def test_local_and_online_are_compared_by_fit_not_channel():
    service = UniversalRevenueRouterService()
    requirement = UserRequirement(
        user_id="u3",
        intent="buy",
        category="air conditioner",
        explicit_requirement=True,
    )

    local = _offer(
        "local",
        suitability=0.80,
        trust=0.90,
        channel=OfferChannel.LOCAL,
        route_type=RevenueRouteType.LOCAL_MATCH,
    )
    online = _offer(
        "online",
        suitability=0.91,
        trust=0.88,
        channel=OfferChannel.ONLINE,
        route_type=RevenueRouteType.AFFILIATE_REDIRECT,
    )

    decision = service.decide(requirement, [local, online])

    assert decision.selected_offer.offer_id == "online"


def test_partner_handoff_is_blocked_until_user_consents():
    service = UniversalRevenueRouterService()
    insurance_offer = RevenueOffer(
        offer_id="motor-insurance-partner",
        partner_id="licensed-partner",
        category="motor insurance",
        route_type=RevenueRouteType.PARTNER_LEAD,
        channel=OfferChannel.PARTNER,
        suitability_score=0.95,
        trust_score=0.95,
        requires_consent=True,
        regulated_handoff=True,
    )
    no_consent = UserRequirement(
        user_id="u4",
        intent="renew insurance",
        category="motor insurance",
        explicit_requirement=True,
        consent_to_partner_handoff=False,
    )

    blocked = service.decide(no_consent, [insurance_offer])
    assert blocked.monetization_allowed is False

    with_consent = UserRequirement(
        user_id="u4",
        intent="renew insurance",
        category="motor insurance",
        explicit_requirement=True,
        consent_to_partner_handoff=True,
    )
    allowed = service.decide(with_consent, [insurance_offer])

    assert allowed.monetization_allowed is True
    assert allowed.selected_offer.route_type is RevenueRouteType.PARTNER_LEAD
    assert allowed.selected_offer.regulated_handoff is True


def test_attribution_starts_open_and_keeps_route_identity():
    service = UniversalRevenueRouterService()
    requirement = UserRequirement(
        user_id="u5",
        intent="buy",
        category="air conditioner",
        explicit_requirement=True,
    )
    offer = _offer(
        "affiliate",
        suitability=0.9,
        trust=0.9,
        channel=OfferChannel.ONLINE,
        route_type=RevenueRouteType.AFFILIATE_REDIRECT,
    )

    attribution = service.create_attribution(requirement, offer)

    assert attribution.attribution_id.startswith("podx_")
    assert attribution.user_id == "u5"
    assert attribution.offer_id == "affiliate"
    assert attribution.status is ConversionStatus.OPEN
    assert attribution.route_type is RevenueRouteType.AFFILIATE_REDIRECT
