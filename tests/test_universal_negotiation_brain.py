from fastapi.testclient import TestClient

from app.api.app_factory import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "podx-negotiation-test.db"))
    app = create_app()
    return TestClient(app), app.state.container


def _accepted(client, container, buyer="app-buyer-n", seller="app-seller-n"):
    demand_id = container.universal_demand_repository.create({
        "user_id": buyer,
        "side": "NEED",
        "domain": "PRODUCT",
        "subject": "rice",
        "quantity": 25,
        "unit": "kg",
        "status": "ACTIVE",
    })
    container.universal_notification_repository.record_interest(demand_id, buyer, seller)
    response = client.post("/debug/interest-action", json={
        "user_id": buyer,
        "request_id": demand_id,
        "responder_user_id": seller,
        "action": "ACCEPT",
    })
    assert response.status_code == 200
    return demand_id, buyer, seller


def _limits(client, demand_id, buyer, seller, asking=220, floor=200):
    response = client.post("/debug/deal-negotiation/seller-limits", json={
        "user_id": seller,
        "request_id": demand_id,
        "buyer_user_id": buyer,
        "asking_price": asking,
        "floor_price": floor,
        "currency": "INR",
    })
    assert response.status_code == 200


def test_offer_inside_seller_range_auto_agrees_and_confirms_deal(tmp_path, monkeypatch):
    client, container = _client(tmp_path, monkeypatch)
    demand_id, buyer, seller = _accepted(client, container)
    _limits(client, demand_id, buyer, seller)

    response = client.post("/debug/deal-negotiation/buyer-offer", json={
        "user_id": buyer,
        "request_id": demand_id,
        "seller_user_id": seller,
        "amount": 205,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "AGREED"
    assert data["final_price"] == 205
    assert data["seller_action_required"] is False

    thread = client.get(f"/debug/deal-thread/{demand_id}/{buyer}/{seller}")
    assert thread.status_code == 200
    assert thread.json()["deal"]["deal_status"] == "CONFIRMED"


def test_offer_above_asking_locks_asking_price(tmp_path, monkeypatch):
    client, container = _client(tmp_path, monkeypatch)
    demand_id, buyer, seller = _accepted(client, container, "app-buyer-high", "app-seller-high")
    _limits(client, demand_id, buyer, seller, asking=220, floor=200)

    response = client.post("/debug/deal-negotiation/buyer-offer", json={
        "user_id": buyer,
        "request_id": demand_id,
        "seller_user_id": seller,
        "amount": 230,
    })
    assert response.status_code == 200
    assert response.json()["status"] == "AGREED"
    assert response.json()["final_price"] == 220


def test_offer_below_floor_escalates_to_seller_and_seller_can_accept(tmp_path, monkeypatch):
    client, container = _client(tmp_path, monkeypatch)
    demand_id, buyer, seller = _accepted(client, container, "app-buyer-low", "app-seller-low")
    _limits(client, demand_id, buyer, seller, asking=220, floor=200)

    offer = client.post("/debug/deal-negotiation/buyer-offer", json={
        "user_id": buyer,
        "request_id": demand_id,
        "seller_user_id": seller,
        "amount": 190,
    })
    assert offer.status_code == 200
    assert offer.json()["status"] == "SELLER_REVIEW"
    assert offer.json()["seller_action_required"] is True

    decision = client.post("/debug/deal-negotiation/seller-decision", json={
        "user_id": seller,
        "request_id": demand_id,
        "buyer_user_id": buyer,
        "action": "ACCEPT",
    })
    assert decision.status_code == 200
    assert decision.json()["status"] == "AGREED"
    assert decision.json()["final_price"] == 190


def test_counter_must_stay_within_seller_limits(tmp_path, monkeypatch):
    client, container = _client(tmp_path, monkeypatch)
    demand_id, buyer, seller = _accepted(client, container, "app-buyer-counter", "app-seller-counter")
    _limits(client, demand_id, buyer, seller, asking=220, floor=200)

    client.post("/debug/deal-negotiation/buyer-offer", json={
        "user_id": buyer,
        "request_id": demand_id,
        "seller_user_id": seller,
        "amount": 190,
    })
    invalid = client.post("/debug/deal-negotiation/seller-decision", json={
        "user_id": seller,
        "request_id": demand_id,
        "buyer_user_id": buyer,
        "action": "COUNTER",
        "amount": 230,
    })
    assert invalid.status_code == 400

    valid = client.post("/debug/deal-negotiation/seller-decision", json={
        "user_id": seller,
        "request_id": demand_id,
        "buyer_user_id": buyer,
        "action": "COUNTER",
        "amount": 210,
    })
    assert valid.status_code == 200
    assert valid.json()["status"] == "COUNTERED"
    assert valid.json()["counter_price"] == 210
