from fastapi.testclient import TestClient

from app.api.app_factory import create_app
from app.api.routes.universal_deals import UniversalDealCreateRequest, _structured_deal_request


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "podx-test.db"))
    app = create_app()
    return TestClient(app), app.state.container


def test_structured_semantic_payload_maps_to_universal_capture():
    payload = UniversalDealCreateRequest(
        user_id="app-semantic-buyer",
        raw_text="THIS TEXT MUST NOT BE PARSED",
        domain="PRODUCT",
        action="BUY",
        entities={"subject": "chicken"},
        category="poultry",
        quantity=2,
        unit="kg",
        price=500,
        currency="INR",
        variant="boneless",
        confidence=0.97,
    )

    structured = _structured_deal_request(payload)

    assert structured is not None
    assert structured["side"] == "NEED"
    assert structured["domain"] == "PRODUCT"
    assert structured["subject"] == "chicken"
    assert structured["quantity"] == 2
    assert structured["unit"] == "kg"
    assert structured["price"] == 500
    assert structured["currency"] == "INR"
    assert structured["confidence"] == 0.97
    assert structured["constraints"]["category"] == "poultry"
    assert structured["constraints"]["variant"] == "boneless"
    assert structured["constraints"]["entities"]["subject"] == "chicken"


def test_incomplete_semantics_preserve_legacy_raw_text_fallback():
    payload = UniversalDealCreateRequest(
        user_id="app-legacy-buyer",
        raw_text="I need rice",
    )

    assert _structured_deal_request(payload) is None


def test_deals_api_complete_semantics_does_not_reparse_raw_text(tmp_path, monkeypatch):
    client, container = _client(tmp_path, monkeypatch)

    def fail_reparse(*args, **kwargs):
        raise AssertionError("complete semantic deal must not be reparsed from raw_text")

    monkeypatch.setattr(container.conversation_service, "process", fail_reparse)

    response = client.post(
        "/deals",
        json={
            "user_id": "app-semantic-buyer",
            "raw_text": "THIS TEXT MUST NOT BE PARSED",
            "domain": "PRODUCT",
            "action": "BUY",
            "entities": {"subject": "chicken"},
            "quantity": 2,
            "unit": "kg",
            "price": 500,
            "currency": "INR",
            "variant": "boneless",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["side"] == "NEED"
    assert body["domain"] == "PRODUCT"
    assert body["subject"] == "chicken"

    stored = container.universal_demand_repository.get(body["deal_id"])
    assert stored is not None
    assert stored["side"] == "NEED"
    assert stored["domain"] == "PRODUCT"
    assert stored["subject"] == "chicken"
    assert stored["constraints"]["variant"] == "boneless"
