from app.services.universal_response_command_service import UniversalResponseCommandService


class FakeDemands:
    def get(self, request_id):
        if int(request_id) == 200:
            return {"id": 200, "subject": "55 inch Samsung Smart TV", "domain": "PRODUCT"}
        if int(request_id) == 100:
            return {"id": 100, "subject": "rice bag", "domain": "PRODUCT"}
        return None


class FakeDeals:
    def __init__(self):
        self.calls = []

    def pending_for_buyer_change(self, sender):
        return {"request_id": 200, "seller_user_id": "tv-seller"}

    def pending_for_seller(self, sender):
        return {"request_id": 100, "buyer_user_id": "rice-buyer"}

    def consume_buyer_change(self, request, buyer, seller, text):
        self.calls.append(("buyer", int(request["id"]), buyer, seller, text))
        return "BUYER_DOUBT_RELAYED"

    def consume_seller_text(self, request, buyer, seller, text):
        self.calls.append(("seller", int(request["id"]), buyer, seller, text))
        return "SELLER_DETAILS_PARSED"

    def pending_for_buyer_summary(self, sender):
        return None


class FakeContextRouter:
    def should_consume_as_deal_followup(self, request, text):
        return True


class FakeNotifications:
    pass


class FakeNotificationRepository:
    pass


def test_explicit_buyer_doubt_state_wins_when_same_user_is_also_pending_seller():
    service = UniversalResponseCommandService.__new__(UniversalResponseCommandService)
    service.demands = FakeDemands()
    service.notifications = FakeNotifications()
    service.notification_repository = FakeNotificationRepository()
    service.deals = FakeDeals()
    service.context_router = FakeContextRouter()

    reply = service.process_text("same-user", "ఈ TVకి warranty ఉందా? installation freeనా?")

    assert reply == "BUYER_DOUBT_RELAYED"
    assert service.deals.calls == [
        ("buyer", 200, "same-user", "tv-seller", "ఈ TVకి warranty ఉందా? installation freeనా?"),
    ]
