import json

from app.repositories.catering_catalog_repository import CateringCatalogRepository
from app.repositories.catering_menu_pending_repository import CateringMenuPendingRepository
from app.services.catering_menu_ai_service import CateringMenuAIService


class FakeResponse:
    def __init__(self, payload):
        self.text = json.dumps(payload)


class FakeModels:
    def __init__(self, payload):
        self.payload = payload

    def generate_content(self, **kwargs):
        return FakeResponse(self.payload)


class FakeClient:
    def __init__(self, payload):
        self.models = FakeModels(payload)


def build(tmp_path, payload):
    db = str(tmp_path / "podx.db")
    catalog = CateringCatalogRepository(db)
    pending = CateringMenuPendingRepository(db)
    catalog.enable_provider("caterer", "Caterer")
    service = CateringMenuAIService("", catalog, pending, client=FakeClient(payload))
    return service, catalog, pending


def test_ai_menu_waits_for_confirmation_then_saves_deduped_items(tmp_path):
    service, catalog, pending = build(
        tmp_path,
        {
            "menu_detected": True,
            "confidence": 0.95,
            "items": [
                {"name": "Chicken Biryani", "price": 250, "price_basis": "per_plate"},
                {"name": "Sweet", "price": 40, "price_basis": "item"},
                {"name": "Chicken Biryani", "price": 250, "price_basis": "per_plate"},
            ],
        },
    )
    reply = service.process_media("caterer", b"fake-image", "image/jpeg", "media-1", caption="menu")
    assert "2 item(s)" in reply
    assert "CMENU CONFIRM" in reply
    assert catalog.list_items("caterer") == []
    assert len(pending.get("caterer")["items"]) == 2

    confirmed = service.process_text("caterer", "CMENU CONFIRM")
    assert "2 menu item(s)" in confirmed
    items = catalog.list_items("caterer")
    assert len(items) == 2
    assert {item["item_name"] for item in items} == {"Chicken Biryani", "Sweet"}
    assert pending.get("caterer") is None


def test_ai_menu_cancel_discards_pending_items(tmp_path):
    service, catalog, pending = build(
        tmp_path,
        {"menu_detected": True, "confidence": 0.9, "items": [{"name": "Paneer Curry"}]},
    )
    service.process_media("caterer", b"fake-pdf", "application/pdf", "doc-1", filename="menu.pdf")
    assert pending.get("caterer") is not None
    reply = service.process_text("caterer", "CMENU CANCEL")
    assert "save చేయలేదు" in reply
    assert pending.get("caterer") is None
    assert catalog.list_items("caterer") == []


def test_non_menu_media_falls_back_to_existing_image_flow(tmp_path):
    service, catalog, pending = build(
        tmp_path,
        {"menu_detected": False, "confidence": 0.99, "items": []},
    )
    assert service.process_media("caterer", b"photo", "image/jpeg", "media-x") is None
    assert pending.get("caterer") is None
