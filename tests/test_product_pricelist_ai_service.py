from types import SimpleNamespace

from app.repositories.product_catalog_repository import ProductCatalogRepository
from app.repositories.product_pricelist_pending_repository import ProductPriceListPendingRepository
from app.services.product_pricelist_ai_service import ProductPriceListAIService


class FakeModels:
    def __init__(self, text):
        self.text = text
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(text=self.text)


class FakeClient:
    def __init__(self, text):
        self.models = FakeModels(text)


class SellerUsers:
    def find_by_whatsapp_mobile(self, user_id):
        return {"registration_complete": 1, "role": "SELLER"}

    def list_capabilities(self, user_id):
        return ["SELLER"]


class BuyerUsers:
    def find_by_whatsapp_mobile(self, user_id):
        return {"registration_complete": 1, "role": "BUYER"}

    def list_capabilities(self, user_id):
        return ["BUYER"]


def _output():
    return '''{
      "price_list_detected": true,
      "items": [
        {"name":"Sona Masoori Rice","brand":"Local","variant":"25 kg","quantity":25,"unit":"kg","price":1450,"currency":"INR","stock_status":"IN_STOCK","delivery_available":true},
        {"name":"Sunflower Oil","brand":"Fresh","variant":"1 L","quantity":1,"unit":"L","price":130,"currency":"INR","stock_status":"IN_STOCK","delivery_available":false}
      ],
      "confidence": 0.97
    }'''


def test_price_list_requires_confirmation_before_catalog_save(tmp_path):
    db = str(tmp_path / "price.db")
    catalog = ProductCatalogRepository(db)
    pending = ProductPriceListPendingRepository(db)
    service = ProductPriceListAIService("key", catalog, pending, user_repository=SellerUsers(), client=FakeClient(_output()))

    reply = service.process_media("seller1", b"image", "image/jpeg", "media1")
    assert "PLIST CONFIRM" in reply
    assert catalog.find_active("seller1", "Sona Masoori Rice") is None
    assert len(pending.get("seller1")["items"]) == 2

    confirm = service.process_text("seller1", "PLIST CONFIRM")
    assert "2 product" in confirm
    rice = catalog.find_active("seller1", "Sona Masoori Rice")
    assert rice["price"] == 1450
    assert rice["quantity"] == 25
    assert pending.get("seller1") is None


def test_price_list_cancel_does_not_save(tmp_path):
    db = str(tmp_path / "cancel.db")
    catalog = ProductCatalogRepository(db)
    pending = ProductPriceListPendingRepository(db)
    service = ProductPriceListAIService("key", catalog, pending, user_repository=SellerUsers(), client=FakeClient(_output()))
    assert service.process_media("seller2", b"pdf", "application/pdf", "media2")
    assert "save చేయలేదు" in service.process_text("seller2", "PLIST CANCEL")
    assert catalog.find_active("seller2", "Sunflower Oil") is None


def test_buyer_media_without_price_list_caption_bypasses_ai(tmp_path):
    db = str(tmp_path / "buyer.db")
    service = ProductPriceListAIService(
        "key",
        ProductCatalogRepository(db),
        ProductPriceListPendingRepository(db),
        user_repository=BuyerUsers(),
        client=FakeClient(_output()),
    )
    assert service.process_media("buyer", b"image", "image/jpeg", "m") is None
    assert service.client.models.calls == 0


def test_explicit_price_list_caption_allows_media_intake(tmp_path):
    db = str(tmp_path / "caption.db")
    service = ProductPriceListAIService(
        "key",
        ProductCatalogRepository(db),
        ProductPriceListPendingRepository(db),
        user_repository=BuyerUsers(),
        client=FakeClient(_output()),
    )
    reply = service.process_media("shop", b"image", "image/jpeg", "m", caption="My price list")
    assert "PLIST CONFIRM" in reply


def test_fast_webhook_routes_product_price_list_after_catering():
    source = open("app/api/routes/fast_webhook.py", encoding="utf-8").read()
    assert "product_buyer_runtime_service.price_list_ai.process_media" in source
    assert source.index("catering_menu_ai_service.process_media") < source.index("product_buyer_runtime_service.price_list_ai.process_media")
