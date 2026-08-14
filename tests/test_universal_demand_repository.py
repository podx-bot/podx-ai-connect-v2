from app.repositories.universal_demand_repository import UniversalDemandRepository


def test_need_and_offer_persist_and_find_each_other(tmp_path):
    repo = UniversalDemandRepository(str(tmp_path / "podx-test.db"))

    need_id = repo.create({
        "user_id": "buyer-1",
        "side": "NEED",
        "domain": "PRODUCT",
        "subject": "sona masoori rice",
        "quantity": 25,
        "unit": "kg",
        "price": 900,
        "currency": "INR",
        "latitude": 16.50,
        "longitude": 80.64,
        "source": "image",
        "media_ref": "wa-media-1",
    })
    offer_id = repo.create({
        "user_id": "seller-1",
        "side": "OFFER",
        "domain": "PRODUCT",
        "subject": "sona masoori rice bag",
        "quantity": 25,
        "unit": "kg",
        "price": 880,
        "currency": "INR",
        "latitude": 16.51,
        "longitude": 80.65,
    })

    assert repo.get(need_id)["source"] == "image"
    matches = repo.list_opposite_active("NEED", "PRODUCT")
    assert [m["id"] for m in matches] == [offer_id]


def test_closed_records_are_not_candidates(tmp_path):
    repo = UniversalDemandRepository(str(tmp_path / "podx-test.db"))
    offer_id = repo.create({"user_id": "seller", "side": "OFFER", "domain": "SERVICE", "subject": "electrician"})
    repo.update_status(offer_id, "CLOSED")
    assert repo.list_opposite_active("NEED", "SERVICE") == []
