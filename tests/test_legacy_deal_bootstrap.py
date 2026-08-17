from app.services.universal_aware_conversation_service import UniversalAwareConversationService


class FakeNotificationRepository:
    def latest_interest_for_buyer(self, buyer):
        return {
            "request_id": 77,
            "requester_user_id": buyer,
            "responder_user_id": "seller",
            "requester_status": "ACCEPTED",
            "responder_status": "INTERESTED",
            "qualification_status": "READY_FOR_BUYER",
        }


class FakeDemandRepository:
    def get(self, request_id):
        assert request_id == 77
        return {
            "id": 77,
            "user_id": "buyer",
            "side": "NEED",
            "domain": "PRODUCT",
            "subject": "chicken",
            "quantity": 5,
            "unit": "kg",
            "status": "ACTIVE",
        }


class FakeDealRepository:
    def __init__(self):
        self.row = None

    def get(self, request_id, seller):
        return self.row


class FakeDeals:
    def __init__(self):
        self.repository = FakeDealRepository()
        self.calls = []

    def start(self, request, buyer, seller):
        self.calls.append(("start", request["id"], buyer, seller))
        self.repository.row = {
            "request_id": request["id"],
            "buyer_user_id": buyer,
            "seller_user_id": seller,
            "status": "WAITING_SELLER_DETAILS",
        }
        return {"status": "WAITING_SELLER_DETAILS"}

    def ask_for_change(self, request, buyer, seller):
        self.calls.append(("ask", request["id"], buyer, seller))
        self.repository.row["status"] = "WAITING_BUYER_CHANGE"
        return "ready"

    def consume_buyer_change(self, request, buyer, seller, text):
        self.calls.append(("relay", request["id"], buyer, seller, text))
        return "✅ మీ clarification sellerకి పంపాను."


class FakeResponseCommands:
    def __init__(self):
        self.notification_repository = FakeNotificationRepository()
        self.demands = FakeDemandRepository()
        self.deals = FakeDeals()

    def process_text(self, sender_mobile, message):
        return None

    @staticmethod
    def _looks_like_deal_change(text):
        lowered = text.casefold()
        return any(term in lowered for term in ("rate", "price", "quality", "క్వాలిటీ", "రేట్", "ఎంత"))


class FakeBaseConversation:
    user_repository = None
    session_registry = None

    def process(self, sender_mobile, message):
        return "base"


def test_accepted_pre_feature_match_bootstraps_and_relays_buyer_question():
    commands = FakeResponseCommands()
    service = UniversalAwareConversationService(commands, FakeBaseConversation())

    reply = service._matched_product_faq(
        "buyer",
        "5 కేజీలు కావాలి, మంచి క్వాలిటీ కావాలి. రేట్ ఎంత?",
    )

    assert "sellerకి పంపాను" in reply
    assert commands.deals.calls[0] == ("start", 77, "buyer", "seller")
    assert commands.deals.calls[1] == ("ask", 77, "buyer", "seller")
    assert commands.deals.calls[2][0] == "relay"
    assert "రేట్ ఎంత" in commands.deals.calls[2][-1]
