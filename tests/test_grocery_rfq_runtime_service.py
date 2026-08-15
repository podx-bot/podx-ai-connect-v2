from app.repositories.grocery_rfq_repository import GroceryRFQRepository
from app.repositories.product_catalog_repository import ProductCatalogRepository
from app.services.grocery_rfq_runtime_service import GroceryRFQRuntimeService
from app.services.grocery_rfq_service import GroceryRFQService


class FakeWhatsApp:
    def __init__(self):
        self.sent = []

    def send_text_message(self, mobile, text):
        self.sent.append((str(mobile), str(text)))


class Users:
    def __init__(self, complete):
        self.complete = complete

    def find_by_whatsapp_mobile(self, user_id):
        return {"registration_complete": 1 if self.complete else 0}


def resolver(user_id):
    return {"mobile": str(user_id)}


def build_runtime(tmp_path):
    db_path = str(tmp_path / "podx.db")
    repo = GroceryRFQRepository(db_path)
    ProductCatalogRepository(db_path)
    whatsapp = FakeWhatsApp()
    runtime = GroceryRFQRuntimeService(repo, GroceryRFQService(repo), whatsapp, resolver)
    return db_path, repo, whatsapp, runtime


def test_parse_multi_item_grocery_list():
    items = GroceryRFQRuntimeService._parse_items("Grocery: rice 5kg, oil 1L, sugar 2kg")
    assert [row["item_name"] for row in items] == ["rice", "oil", "sugar"]
    assert items[0]["quantity"] == 5.0
    assert items[1]["unit"].casefold() == "l"


def test_unregistered_grocery_message_passes_to_onboarding(tmp_path):
    _, repo, whatsapp, _ = build_runtime(tmp_path)
    runtime = GroceryRFQRuntimeService(repo, GroceryRFQService(repo), whatsapp, resolver, user_repository=Users(False))
    assert runtime.process("new-user", "Grocery: rice 5kg, oil 1L") is None
    assert repo.latest_open_for_buyer("new-user") is None


def test_grocery_request_targets_catalog_seller_once(tmp_path):
    db_path, repo, whatsapp, runtime = build_runtime(tmp_path)
    catalog = ProductCatalogRepository(db_path)
    catalog.upsert_product("seller-1", "rice", price=60, stock_status="IN_STOCK")
    catalog.upsert_product("seller-1", "oil", price=150, stock_status="IN_STOCK")
    catalog.upsert_product("seller-2", "soap", price=30, stock_status="IN_STOCK")

    reply = runtime.process("buyer-1", "Grocery: rice 5kg, oil 1L, sugar 2kg")

    assert "1 matching seller" in reply
    assert len(whatsapp.sent) == 1
    assert whatsapp.sent[0][0] == "seller-1"
    assert "GQUOTE" in whatsapp.sent[0][1]


def test_seller_quote_is_saved_ranked_and_buyer_notified(tmp_path):
    db_path, repo, whatsapp, runtime = build_runtime(tmp_path)
    rfq_id = repo.create_rfq("buyer-1", [
        {"item_name": "rice", "quantity": 5, "unit": "kg"},
        {"item_name": "oil", "quantity": 1, "unit": "L"},
    ])
    assert repo.add_target(rfq_id, "seller-1") is True

    reply = runtime.process("seller-1", f"GQUOTE {rfq_id} rice=300, oil=150, delivery=30")

    assert "2/2 items priced" in reply
    quotes = repo.submitted_quotes(rfq_id)
    assert len(quotes) == 1
    assert len(quotes[0]["items"]) == 2
    ranked = GroceryRFQService(repo).rank(rfq_id)
    assert ranked["best_value"]["total"] == 480.0
    assert whatsapp.sent[-1][0] == "buyer-1"
    assert "కొత్త seller quote" in whatsapp.sent[-1][1]


def test_grocery_quotes_command_returns_comparison(tmp_path):
    _, repo, _, runtime = build_runtime(tmp_path)
    rfq_id = repo.create_rfq("buyer-1", [{"item_name": "rice", "quantity": 5, "unit": "kg"}])
    repo.add_target(rfq_id, "seller-1")
    runtime.process("seller-1", f"GQUOTE {rfq_id} rice=300, delivery=20")

    reply = runtime.process("buyer-1", "Grocery Quotes")

    assert f"RFQ #{rfq_id}" in reply
    assert "Best Value" in reply
    assert "₹320" in reply
