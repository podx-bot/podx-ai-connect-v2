from app.repositories.deal_discussion_repository import DealDiscussionRepository


def test_pending_seller_deal_follows_latest_interaction_not_row_id(tmp_path):
    repo = DealDiscussionRepository(str(tmp_path / "podx.db"))

    repo.start(101, "buyer-old", "seller", {"quantity": 1})
    repo.start(202, "buyer-new", "seller", {"quantity": 2})

    # Re-open/update the older request after the newer row already exists.
    # Routing must follow the deal most recently interacted with, not simply
    # the largest database row id.
    repo.start(101, "buyer-old", "seller", {"quantity": 3})

    pending = repo.latest_for_seller(
        "seller",
        ("WAITING_SELLER_DETAILS", "WAITING_SELLER_REVISION"),
    )

    assert pending is not None
    assert pending["request_id"] == 101
    assert pending["buyer_user_id"] == "buyer-old"
    assert pending["details"]["quantity"] == 3


def test_pending_buyer_deal_follows_latest_interaction_not_row_id(tmp_path):
    repo = DealDiscussionRepository(str(tmp_path / "podx.db"))

    repo.start(11, "buyer", "seller-a", {})
    repo.start(22, "buyer", "seller-b", {})
    repo.save_seller_details(11, "seller-a", {"price": 100}, "₹100")

    pending = repo.latest_for_buyer(
        "buyer",
        ("WAITING_BUYER_CONFIRM", "WAITING_SELLER_DETAILS", "WAITING_SELLER_REVISION"),
    )

    assert pending is not None
    assert pending["request_id"] == 11
    assert pending["seller_user_id"] == "seller-a"
