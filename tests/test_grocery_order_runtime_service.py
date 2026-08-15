from app.repositories.grocery_order_repository import GroceryOrderRepository
from app.repositories.grocery_rfq_repository import GroceryRFQRepository
from app.repositories.local_dispatch_repository import LocalDispatchRepository
from app.services.grocery_order_runtime_service import GroceryOrderRuntimeService


def resolver(user_id):
    return {"mobile": str(user_id), "area": "Seller Area"}


def build(tmp_path):
    db_path = str(tmp_path / "podx.db")
    rfqs = GroceryRFQRepository(db_path)
    orders = GroceryOrderRepository(db_path)
    dispatch = LocalDispatchRepository(db_path)
    runtime = GroceryOrderRuntimeService(rfqs, orders, dispatch, resolver)
    return rfqs, orders, dispatch, runtime


def seed_quote(rfqs):
    rfq_id = rfqs.create_rfq("buyer-1", [
        {"item_name": "rice", "quantity": 5, "unit": "kg"},
        {"item_name": "oil", "quantity": 1, "unit": "L"},
    ])
    items = rfqs.list_items(rfq_id)
    quote_id = rfqs.start_quote(rfq_id, "seller-1", delivery_fee=30)
    rfqs.set_item_quote(quote_id, items[0]["id"], 300)
    rfqs.set_item_quote(quote_id, items[1]["id"], 150)
    rfqs.submit_quote(quote_id)
    return rfq_id


def test_buyer_selects_submitted_grocery_quote(tmp_path):
    rfqs, orders, _, runtime = build(tmp_path)
    rfq_id = seed_quote(rfqs)

    reply = runtime.process("buyer-1", f"GSELECT {rfq_id} seller-1")

    assert "Grocery Order #" in reply
    assert "₹480" in reply
    order = orders.get(1)
    assert order["seller_user_id"] == "seller-1"
    assert order["status"] == "ADDRESS_REQUIRED"
    assert rfqs.get_rfq(rfq_id)["status"] == "SELECTED"


def test_wrong_buyer_cannot_select_quote(tmp_path):
    rfqs, orders, _, runtime = build(tmp_path)
    rfq_id = seed_quote(rfqs)

    reply = runtime.process("buyer-2", f"GSELECT {rfq_id} seller-1")

    assert "మీ open grocery request కాదు" in reply
    assert orders.get(1) is None


def test_delivery_address_creates_local_dispatch_task(tmp_path):
    rfqs, orders, dispatch, runtime = build(tmp_path)
    rfq_id = seed_quote(rfqs)
    runtime.process("buyer-1", f"GSELECT {rfq_id} seller-1")

    reply = runtime.process("buyer-1", "GADDRESS 1 Vijayawada Benz Circle, Door 10")

    assert "Dispatch Task #1" in reply
    order = orders.get(1)
    assert order["status"] == "DISPATCH_OPEN"
    task = dispatch.get(1)
    assert task["order_ref"] == "GROCERY-1"
    assert task["seller_user_id"] == "seller-1"
    assert task["buyer_user_id"] == "buyer-1"
    assert task["drop_text"] == "Vijayawada Benz Circle, Door 10"
