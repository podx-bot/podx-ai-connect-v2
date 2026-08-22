from fastapi.testclient import TestClient

from app.api.app_factory import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "podx-test.db"))
    app = create_app()
    return TestClient(app), app.state.container


def test_in_app_inbox_and_interested_action(tmp_path, monkeypatch):
    client, container = _client(tmp_path, monkeypatch)
    buyer = "app-buyer"
    seller = "app-seller"

    demand_id = container.universal_demand_repository.create({
        "user_id": buyer,
        "side": "NEED",
        "domain": "PRODUCT",
        "subject": "chicken",
        "quantity": 2,
        "unit": "kg",
        "status": "ACTIVE",
    })
    notification_id = container.universal_notification_repository.reserve_notification(
        demand_id, buyer, seller, 1, 1.2, 0.9
    )
    container.universal_notification_repository.mark_sent(
        notification_id, f"in-app:{demand_id}:{seller}"
    )

    inbox = client.get(f"/debug/inbox/{seller}")
    assert inbox.status_code == 200
    data = inbox.json()
    assert data["match_count"] == 1
    assert data["matches"][0]["subject"] == "chicken"
    assert data["matches"][0]["actions"] == ["INTERESTED", "NOT_INTERESTED"]

    action = client.post("/debug/match-action", json={
        "user_id": seller,
        "request_id": demand_id,
        "action": "INTERESTED",
    })
    assert action.status_code == 200
    assert action.json()["status"] == "IN_APP_WAITING_REQUESTER_CONSENT"

    buyer_inbox = client.get(f"/debug/inbox/{buyer}")
    assert buyer_inbox.status_code == 200
    updates = buyer_inbox.json()["interest_updates"]
    current = [item for item in updates if item["request_id"] == demand_id]
    assert len(current) == 1
    assert current[0]["responder_user_id"] == seller
    assert current[0]["actions"] == ["ACCEPT", "DECLINE"]


def test_not_interested_dismisses_match(tmp_path, monkeypatch):
    client, container = _client(tmp_path, monkeypatch)
    buyer = "app-buyer-2"
    seller = "app-seller-2"
    demand_id = container.universal_demand_repository.create({
        "user_id": buyer,
        "side": "NEED",
        "domain": "PRODUCT",
        "subject": "eggs",
        "status": "ACTIVE",
    })
    notification_id = container.universal_notification_repository.reserve_notification(
        demand_id, buyer, seller, 1, 2.0, 0.8
    )
    container.universal_notification_repository.mark_sent(notification_id, "in-app:test")

    action = client.post("/debug/match-action", json={
        "user_id": seller,
        "request_id": demand_id,
        "action": "NOT_INTERESTED",
    })
    assert action.status_code == 200
    assert action.json()["status"] == "DISMISSED"

    inbox = client.get(f"/debug/inbox/{seller}")
    assert inbox.status_code == 200
    assert inbox.json()["match_count"] == 0
