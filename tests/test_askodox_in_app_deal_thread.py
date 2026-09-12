from fastapi.testclient import TestClient

from app.api.app_factory import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "podx-test.db"))
    app = create_app()
    return TestClient(app), app.state.container


def _seed_interest(container, buyer="app-buyer", seller="app-seller"):
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
    return demand_id


def test_buyer_accept_opens_in_app_conversation(tmp_path, monkeypatch):
    client, container = _client(tmp_path, monkeypatch)
    buyer, seller = "app-buyer", "app-seller"
    demand_id = _seed_interest(container, buyer, seller)

    decision = client.post("/debug/interest-action", json={
        "user_id": buyer,
        "request_id": demand_id,
        "responder_user_id": seller,
        "action": "ACCEPT",
    })
    assert decision.status_code == 200
    assert decision.json()["status"] == "IN_APP_READY_FOR_BUYER"
    assert decision.json()["conversation_ready"] is True

    sent = client.post("/debug/deal-message", json={
        "user_id": buyer,
        "request_id": demand_id,
        "other_user_id": seller,
        "message": "Can you deliver by 6 PM?",
    })
    assert sent.status_code == 200
    assert sent.json()["status"] == "SENT"
    assert sent.json()["channel"] == "in_app"

    thread = client.get(f"/debug/deal-thread/{demand_id}/{seller}/{buyer}")
    assert thread.status_code == 200
    data = thread.json()
    assert data["status"] == "OPEN"
    assert data["channel"] == "in_app"
    assert data["deal"]["subject"] == "chicken"
    assert any(m["message_text"] == "Can you deliver by 6 PM?" for m in data["messages"])


def test_decline_keeps_conversation_closed(tmp_path, monkeypatch):
    client, container = _client(tmp_path, monkeypatch)
    buyer, seller = "app-buyer-2", "app-seller-2"
    demand_id = _seed_interest(container, buyer, seller)

    decision = client.post("/debug/interest-action", json={
        "user_id": buyer,
        "request_id": demand_id,
        "responder_user_id": seller,
        "action": "DECLINE",
    })
    assert decision.status_code == 200
    assert decision.json()["status"] == "DECLINED"
    assert decision.json()["conversation_ready"] is False

    sent = client.post("/debug/deal-message", json={
        "user_id": seller,
        "request_id": demand_id,
        "other_user_id": buyer,
        "message": "Hello",
    })
    assert sent.status_code == 409


def test_non_participant_cannot_read_accepted_thread(tmp_path, monkeypatch):
    client, container = _client(tmp_path, monkeypatch)
    buyer, seller = "app-buyer-3", "app-seller-3"
    demand_id = _seed_interest(container, buyer, seller)
    container.universal_notification_repository.set_seller_decision(demand_id, seller, True)

    response = client.get(f"/debug/deal-thread/{demand_id}/app-outsider/{seller}")
    assert response.status_code == 403


def test_repeated_inputs_stay_on_one_active_deal_thread(tmp_path, monkeypatch):
    client, container = _client(tmp_path, monkeypatch)
    buyer, seller = "app-kernel-buyer", "app-kernel-seller"
    demand_id = _seed_interest(container, buyer, seller)

    decision = client.post("/debug/interest-action", json={
        "user_id": buyer,
        "request_id": demand_id,
        "responder_user_id": seller,
        "action": "ACCEPT",
    })
    assert decision.status_code == 200
    assert decision.json()["conversation_ready"] is True

    messages = [
        "TEXT: Need delivery by 6 PM",
        "VOICE: Please keep the same chicken order",
        "OCR: Photo says 2 kg chicken",
    ]
    for message in messages:
        sent = client.post("/debug/deal-message", json={
            "user_id": buyer,
            "request_id": demand_id,
            "other_user_id": seller,
            "message": message,
        })
        assert sent.status_code == 200
        assert sent.json()["status"] == "SENT"

    thread = client.get(f"/debug/deal-thread/{demand_id}/{buyer}/{seller}")
    assert thread.status_code == 200
    data = thread.json()
    assert data["status"] == "OPEN"
    assert data["deal"]["subject"] == "chicken"
    thread_text = [m["message_text"] for m in data["messages"]]
    for message in messages:
        assert message in thread_text

    thread_count = container.database.fetchone(
        """
        SELECT COUNT(*) AS total
        FROM in_app_deal_threads
        WHERE request_id=? AND buyer_user_id=? AND seller_user_id=?
        """,
        (demand_id, buyer, seller),
    )
    assert int(thread_count["total"]) == 1
