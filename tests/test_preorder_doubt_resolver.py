from app.services.universal_response_command_service import UniversalResponseCommandService


class FakeDemandRepository:
    def __init__(self, request):
        self.request = request

    def get(self, request_id):
        return self.request if int(request_id) == int(self.request["id"]) else None


class FakeDealRepository:
    def __init__(self, deal):
        self.deal = dict(deal)
        self.marked = False

    def get(self, request_id, seller):
        if int(request_id) != int(self.deal["request_id"]):
            return None
        if str(seller) != str(self.deal["seller_user_id"]):
            return None
        return dict(self.deal)

    def mark_waiting_buyer_change(self, request_id, seller):
        self.marked = True
        self.deal["status"] = "WAITING_BUYER_CHANGE"


class FakeDeals:
    def __init__(self, deal, confirmed=True):
        self.repository = FakeDealRepository(deal)
        self.confirmed = confirmed

    def is_confirmed(self, request_id, seller):
        return self.confirmed


class FakeNotifications:
    def __init__(self):
        self.sent = []
        self.final_confirm_calls = 0
        self.qualify_status = "WAITING_FINAL_CONFIRM"

    def _send_buttons_or_text(self, mobile, body, buttons):
        self.sent.append({"mobile": mobile, "body": body, "buttons": buttons})
        return {"success": True}

    def qualify_lead(self, request, buyer, seller, address):
        return {"status": self.qualify_status}

    def final_confirm(self, request, buyer, seller, accepted):
        self.final_confirm_calls += 1
        return {"status": "CONVERTED"}


class FakeNotificationRepository:
    pass


def build_service(*, confirmed=True):
    request = {
        "id": 77,
        "user_id": "seller-1",
        "side": "OFFER",
        "subject": "55 inch smart TV",
        "price": 42000,
    }
    deal = {
        "request_id": 77,
        "buyer_user_id": "buyer-1",
        "seller_user_id": "seller-1",
        "status": "CONFIRMED",
        "details": {"rate": 42000},
    }
    service = UniversalResponseCommandService.__new__(UniversalResponseCommandService)
    service.demands = FakeDemandRepository(request)
    service.notifications = FakeNotifications()
    service.notification_repository = FakeNotificationRepository()
    service.deals = FakeDeals(deal, confirmed=confirmed)
    return service


def test_final_summary_followup_offers_confirm_question_and_direct_talk():
    service = build_service()

    service._send_preorder_options("buyer-1", 77, "seller-1")

    assert len(service.notifications.sent) == 1
    message = service.notifications.sent[0]
    ids = [button["id"] for button in message["buttons"]]
    assert ids == [
        "FINAL_CONFIRM 77 seller-1",
        "DEAL_QUESTION 77 seller-1",
        "DIRECT_TALK 77 seller-1",
    ]
    assert "ఇంకేమైనా" in message["body"]


def test_deal_question_moves_confirmed_deal_into_private_buyer_question_state():
    service = build_service()

    reply = service._deal_question("buyer-1", 77, "seller-1")

    assert service.deals.repository.marked is True
    assert service.deals.repository.deal["status"] == "WAITING_BUYER_CHANGE"
    assert "text/voice" in reply
    assert "private" in reply


def test_final_confirm_is_blocked_while_seller_doubt_is_pending():
    service = build_service(confirmed=False)

    reply = service._final_order("buyer-1", 77, "seller-1", True)

    assert "pending" in reply
    assert service.notifications.final_confirm_calls == 0


def test_address_completion_sends_preorder_decision_options():
    service = build_service()

    reply = service._save_address(
        "buyer-1",
        77,
        "seller-1",
        "12-34 Main Road Vuyyuru 521165",
    )

    assert "Sellerని అడగండి" in reply
    assert len(service.notifications.sent) == 1
    button_ids = [button["id"] for button in service.notifications.sent[0]["buttons"]]
    assert "DEAL_QUESTION 77 seller-1" in button_ids
