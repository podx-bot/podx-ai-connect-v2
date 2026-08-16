from app.repositories.universal_rfq_repository import UniversalRFQRepository
from app.services.universal_rfq_service import UniversalRFQService


def build(tmp_path):
    repo = UniversalRFQRepository(str(tmp_path / "rfq.db"))
    return repo, UniversalRFQService(repo)


def test_catering_rfq_full_match_ranks_above_cheaper_partial_match(tmp_path):
    repo, service = build(tmp_path)
    rfq_id = repo.create_rfq(
        requester_user_id="buyer",
        rfq_type="CATERING",
        title="Marriage catering",
        location_text="Vijayawada",
        event_date="2026-08-25",
        guest_count=300,
        items=[
            {"name": "Chicken Biryani", "quantity": 300, "unit": "plate"},
            {"name": "Paneer Curry", "quantity": 300, "unit": "plate"},
            {"name": "Sweet", "quantity": 300, "unit": "piece"},
        ],
    )
    items = repo.list_items(rfq_id)
    repo.add_target(rfq_id, "caterer-full", match_score=0.95, distance_km=3.0)
    repo.add_target(rfq_id, "caterer-partial", match_score=0.90, distance_km=2.0)

    full = repo.start_quote(rfq_id, "caterer-full", provider_total=120000, reliability_score=0.9)
    for item in items:
        repo.set_item_quote(full, item["id"], available=True, included=True)
    repo.submit_quote(full)

    partial = repo.start_quote(rfq_id, "caterer-partial", provider_total=80000, reliability_score=0.95)
    repo.set_item_quote(partial, items[0]["id"], available=True, included=True)
    repo.set_item_quote(partial, items[1]["id"], available=True, included=True)
    repo.set_item_quote(partial, items[2]["id"], available=False, included=False)
    repo.submit_quote(partial)

    comparison = service.compare_quotes(rfq_id)
    assert comparison["status"] == "OK"
    assert comparison["quotes"][0]["provider_user_id"] == "caterer-full"
    assert comparison["quotes"][0]["coverage_percent"] == 100.0
    assert comparison["quotes"][1]["coverage_percent"] == 66.7
    assert comparison["quotes"][1]["missing_items"] == ["Sweet"]
    assert comparison["quotes"][1]["label"] == "PARTIAL_MATCH"


def test_universal_rfq_calculates_total_and_owner_can_select(tmp_path):
    repo, service = build(tmp_path)
    rfq_id = repo.create_rfq(
        "buyer",
        "SERVICE",
        [{"name": "Serving Staff", "quantity": 5, "unit": "person"}],
        title="Function serving staff",
    )
    item = repo.list_items(rfq_id)[0]
    repo.add_target(rfq_id, "provider")
    quote_id = repo.start_quote(rfq_id, "provider", service_fee=100, delivery_fee=50)
    repo.set_item_quote(quote_id, item["id"], unit_price=500)
    repo.submit_quote(quote_id)

    comparison = service.compare_quotes(rfq_id)
    assert comparison["quotes"][0]["total"] == 2650.0
    assert service.select_quote(rfq_id, quote_id, "wrong-user")["status"] == "NOT_SELECTABLE"
    result = service.select_quote(rfq_id, quote_id, "buyer")
    assert result["status"] == "SELECTED"
    stored = repo.get_rfq(rfq_id)
    assert stored["status"] == "SELECTED"
    assert int(stored["selected_quote_id"]) == quote_id


def test_unknown_rfq_type_is_safely_stored_as_other(tmp_path):
    repo, _ = build(tmp_path)
    rfq_id = repo.create_rfq("buyer", "CUSTOM_NEW_DOMAIN", [{"name": "Anything"}])
    assert repo.get_rfq(rfq_id)["rfq_type"] == "OTHER"
