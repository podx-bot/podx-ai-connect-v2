from app.repositories.universal_demand_repository import UniversalDemandRepository
from app.services.universal_matcher import UniversalMatcher


def _repo(tmp_path):
    return UniversalDemandRepository(str(tmp_path / "matcher.db"))


def test_product_need_ranks_near_affordable_offer_first(tmp_path):
    repo = _repo(tmp_path)
    need_id = repo.create({
        "user_id": "buyer",
        "side": "NEED",
        "domain": "PRODUCT",
        "subject": "sona masoori rice 25kg bag",
        "quantity": 25,
        "unit": "kg",
        "price": 900,
        "latitude": 16.50,
        "longitude": 80.64,
    })
    repo.create({
        "user_id": "seller-near",
        "side": "OFFER",
        "domain": "PRODUCT",
        "subject": "sona masoori rice bag",
        "quantity": 25,
        "unit": "kg",
        "price": 880,
        "latitude": 16.505,
        "longitude": 80.645,
    })
    repo.create({
        "user_id": "seller-far",
        "side": "OFFER",
        "domain": "PRODUCT",
        "subject": "sona masoori rice",
        "quantity": 25,
        "unit": "kg",
        "price": 950,
        "latitude": 17.00,
        "longitude": 81.00,
    })

    need = repo.get(need_id)
    matches = UniversalMatcher(repo).find_matches(need)
    assert matches
    assert matches[0]["user_id"] == "seller-near"
    assert matches[0]["distance_km"] < 2


def test_worker_need_matches_employer_worker_need_even_when_both_natural_side_need(tmp_path):
    repo = _repo(tmp_path)
    worker_id = repo.create({
        "user_id": "worker",
        "side": "NEED",
        "domain": "WORK",
        "subject": "tile laying mason",
        "when_text": "today",
        "latitude": 16.50,
        "longitude": 80.64,
    })
    employer_id = repo.create({
        "user_id": "employer",
        "side": "NEED",
        "domain": "WORKERS",
        "subject": "tile laying workers",
        "quantity": 3,
        "when_text": "today",
        "latitude": 16.51,
        "longitude": 80.65,
    })

    matches = UniversalMatcher(repo).find_matches(repo.get(worker_id))
    assert [m["id"] for m in matches] == [employer_id]


def test_unrelated_subject_does_not_match_only_because_it_is_nearby(tmp_path):
    repo = _repo(tmp_path)
    need_id = repo.create({
        "user_id": "buyer",
        "side": "NEED",
        "domain": "PRODUCT",
        "subject": "industrial water pump",
        "latitude": 16.50,
        "longitude": 80.64,
    })
    repo.create({
        "user_id": "seller",
        "side": "OFFER",
        "domain": "PRODUCT",
        "subject": "birthday cake",
        "latitude": 16.50,
        "longitude": 80.64,
    })

    assert UniversalMatcher(repo).find_matches(repo.get(need_id)) == []


def test_closed_records_are_ignored_by_matcher(tmp_path):
    repo = _repo(tmp_path)
    need_id = repo.create({"user_id": "a", "side": "NEED", "domain": "SERVICE", "subject": "solar panel cleaning"})
    offer_id = repo.create({"user_id": "b", "side": "OFFER", "domain": "SERVICE", "subject": "solar panel cleaning"})
    repo.update_status(offer_id, "CLOSED")
    assert UniversalMatcher(repo).find_matches(repo.get(need_id)) == []
