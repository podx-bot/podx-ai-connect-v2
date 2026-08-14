from app.services.universal_matcher import UniversalMatcher
from app.services.universal_targeting_service import UniversalTargetingService


def _distance(a, b):
    return UniversalMatcher._distance_km(a, b)


def _similarity(a, b):
    return UniversalMatcher._subject_similarity(a, b)


def test_targets_related_seller_even_without_exact_product_listing():
    profiles = [
        {
            "user_id": "rice-shop",
            "role": "SELLER",
            "business_type": "rice and grocery store",
            "category": "rice grocery",
            "products": [],
            "latitude": 16.51,
            "longitude": 80.65,
        },
        {
            "user_id": "cake-shop",
            "role": "SELLER",
            "business_type": "bakery birthday cakes",
            "latitude": 16.50,
            "longitude": 80.64,
        },
    ]
    service = UniversalTargetingService(lambda: profiles, _similarity, _distance)
    result = service.build_plan(
        {
            "id": 10,
            "user_id": "buyer",
            "side": "NEED",
            "domain": "PRODUCT",
            "subject": "sona masoori rice",
            "latitude": 16.50,
            "longitude": 80.64,
        }
    )
    assert result["status"] == "TARGETED"
    ids = [t["user_id"] for w in result["waves"] for t in w["targets"]]
    assert "rice-shop" in ids
    assert "cake-shop" not in ids


def test_excludes_requester_and_already_contacted_users():
    profiles = [
        {"user_id": "buyer", "role": "SELLER", "category": "water pump", "latitude": 16.5, "longitude": 80.64},
        {"user_id": "seller-1", "role": "SELLER", "category": "industrial water pump", "latitude": 16.5, "longitude": 80.64},
        {"user_id": "seller-2", "role": "SELLER", "category": "industrial water pump", "latitude": 16.51, "longitude": 80.65},
    ]
    service = UniversalTargetingService(lambda: profiles, _similarity, _distance)
    result = service.build_plan(
        {"user_id": "buyer", "side": "NEED", "domain": "PRODUCT", "subject": "industrial water pump", "latitude": 16.5, "longitude": 80.64},
        already_contacted_user_ids=["seller-1"],
    )
    ids = [t["user_id"] for w in result["waves"] for t in w["targets"]]
    assert ids == ["seller-2"]


def test_returns_hold_when_no_relevant_profiles_exist():
    profiles = [
        {"user_id": "unrelated", "role": "SERVICE_PROVIDER", "skill": "wedding photography", "latitude": 16.5, "longitude": 80.64}
    ]
    service = UniversalTargetingService(lambda: profiles, _similarity, _distance)
    result = service.build_plan(
        {"user_id": "employer", "side": "NEED", "domain": "WORKERS", "subject": "masonry workers", "latitude": 16.5, "longitude": 80.64}
    )
    assert result["status"] == "HOLD"
    assert result["total_targets"] == 0


def test_progressive_radius_puts_near_targets_before_far_targets():
    profiles = [
        {"user_id": "near", "role": "SELLER", "category": "steel rods", "latitude": 16.50, "longitude": 80.64},
        {"user_id": "far", "role": "SELLER", "category": "steel rods", "latitude": 16.72, "longitude": 80.64},
    ]
    service = UniversalTargetingService(lambda: profiles, _similarity, _distance, radii_km=(5, 30))
    result = service.build_plan(
        {"user_id": "buyer", "side": "NEED", "domain": "PRODUCT", "subject": "steel rods", "latitude": 16.50, "longitude": 80.64}
    )
    assert result["waves"][0]["targets"][0]["user_id"] == "near"
    assert any(t["user_id"] == "far" for t in result["waves"][1]["targets"])
