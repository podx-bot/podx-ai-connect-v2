from fastapi.testclient import TestClient

from app.api.app_factory import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "podx-test.db"))
    app = create_app()
    return TestClient(app), app.state.container


def _accepted(client, container, buyer="app-buyer-u", seller="app-seller-u"):
    demand_id = container.universal_demand_repository.create({
        "user_id": buyer,
        "side": "NEED",
        "domain": "PRODUCT",
        "subject": "chicken",
        "quantity": 2,
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
    assert response.json()["conversation_ready"] is True
    return demand_id, buyer, seller


def test_deal_inbox_tracks_unread_and_thread_read_clears_it(tmp_path, monkeypatch):
    client, container = _client(tmp_path, monkeypatch)
    demand_id, buyer, seller = _accepted(client, container)

    seller_inbox = client.get(f"/debug/deal-inbox/{seller}")
    assert seller_inbox.status_code == 200
    assert seller_inbox.json()["total_unread"] == 1

    sent = client.post("/debug/deal-message", json={
        "user_id": buyer,
        "request_id": demand_id,
        "other_user_id": seller,
        "message": "Can you deliver today?",
    })
    assert sent.status_code == 200

    seller_inbox = client.get(f"/debug/deal-inbox/{seller}")
    assert seller_inbox.json()["total_unread"] == 2
    assert seller_inbox.json()["threads"][0]["latest_message"] == "Can you deliver today?"

    thread = client.get(f"/debug/deal-thread/{demand_id}/{seller}/{buyer}")
    assert thread.status_code == 200

    seller_inbox = client.get(f"/debug/deal-inbox/{seller}")
    assert seller_inbox.json()["total_unread"] == 0


def test_deal_status_progression_notifies_other_participant(tmp_path, monkeypatch):
    client, container = _client(tmp_path, monkeypatch)
    demand_id, buyer, seller = _accepted(client, container, "app-buyer-s", "app-seller-s")

    client.get(f"/debug/deal-thread/{demand_id}/{seller}/{buyer}")
    status = client.post("/debug/deal-status", json={
        "user_id": seller,
        "request_id": demand_id,
        "other_user_id": buyer,
        "status": "out for delivery",
    })
    assert status.status_code == 200
    assert status.json()["status"] == "OUT_FOR_DELIVERY"

    buyer_inbox = client.get(f"/debug/deal-inbox/{buyer}")
    assert buyer_inbox.status_code == 200
    assert buyer_inbox.json()["total_unread"] == 1
    assert buyer_inbox.json()["threads"][0]["deal_status"] == "OUT_FOR_DELIVERY"

    buyer_thread = client.get(f"/debug/deal-thread/{demand_id}/{buyer}/{seller}")
    assert buyer_thread.status_code == 200
    assert buyer_thread.json()["deal"]["deal_status"] == "OUT_FOR_DELIVERY"
    assert any(m["message_type"] == "STATUS" for m in buyer_thread.json()["messages"])


def test_completed_deal_closes_universal_request(tmp_path, monkeypatch):
    client, container = _client(tmp_path, monkeypatch)
    demand_id, buyer, seller = _accepted(client, container, "app-buyer-c", "app-seller-c")

    response = client.post("/debug/deal-status", json={
        "user_id": buyer,
        "request_id": demand_id,
        "other_user_id": seller,
        "status": "COMPLETED",
    })
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"
    assert container.universal_demand_repository.get(demand_id)["status"] == "COMPLETED"
