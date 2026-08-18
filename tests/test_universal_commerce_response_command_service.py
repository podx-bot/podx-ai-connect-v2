from app.services.universal_commerce_response_command_service import UniversalCommerceResponseCommandService


class FakeRepo:
    def __init__(self, deal):
        self.deal = deal
        self.marked = []

    def get(self, request_id, seller):
        return dict(self.deal)

    def mark_waiting_buyer_change(self, request_id, seller):
        self.marked.append((request_id, seller))
        self.deal["status"] = "WAITING_BUYER_CHANGE"


class FakeDeals:
    def __init__(self, deal):
        self.repository = FakeRepo(deal)
        self.calls = []

    def pending_for_buyer_change(self, sender):
        return None

    def pending_for_seller(self, sender):
        return None

    def pending_for_buyer_summary(self, sender):
        return None

    def consume_buyer_change(self, request, buyer, seller, text):
        self.calls.append((request["id"], buyer, seller, text))
        return "✅ మీ clarification sellerకి పంపాను."


class FakeDemands:
    def get(self, request_id):
        return {"id": int(request_id), "subject": "55 inch Samsung Smart TV", "domain": "PRODUCT"}


class FakeNotificationsRepo:
    def latest_waiting_final_confirm_for_buyer(self, sender):
        return {"request_id": 77, "requester_user_id": sender, "responder_user_id": "seller"}


class DummyNotifications:
    pass


def test_natural_final_order_question_auto_opens_doubt_relay():
    service = UniversalCommerceResponseCommandService.__new__(UniversalCommerceResponseCommandService)
    service.demands = FakeDemands()
    service.notification_repository = FakeNotificationsRepo()
    service.notifications = DummyNotifications()
    service.deals = FakeDeals({
        "request_id": 77,
        "buyer_user_id": "buyer",
        "seller_user_id": "seller",
        "status": "CONFIRMED",
    })
    from app.services.universal_commerce_conversation_engine import UniversalCommerceConversationEngine
    service.commerce_engine = UniversalCommerceConversationEngine()

    reply = service.process_text("buyer", "ఈ TVకి warranty ఉందా? installation freeనా?")

    assert reply == "✅ మీ clarification sellerకి పంపాను."
    assert service.deals.repository.marked == [(77, "seller")]
    assert service.deals.calls == [(77, "buyer", "seller", "ఈ TVకి warranty ఉందా? installation freeనా?")]
