from app.services.universal_aware_conversation_service import UniversalAwareConversationService


class _NotificationRepo:
    @staticmethod
    def latest_interest_for_buyer(_sender):
        return {
            "request_id": 77,
            "responder_user_id": "old-seller",
            "requester_status": "ACCEPTED",
        }


class _Demands:
    @staticmethod
    def get(_request_id):
        return {
            "id": 77,
            "domain": "PRODUCT",
            "side": "NEED",
            "subject": "Gajakesari Punugu",
        }


class _Commands:
    notification_repository = _NotificationRepo()
    demands = _Demands()
    deals = None

    @staticmethod
    def process_text(sender_mobile, message):
        return None

    @staticmethod
    def _same_deal_context(request, message):
        return False


class _LiveCapture:
    def __init__(self):
        self.calls = []

    def process_text(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return "captured-new-offer"


class _Base:
    user_repository = None
    session_registry = None

    @staticmethod
    def process(sender_mobile, message):
        return "base"


def test_new_seller_offer_bypasses_stale_matched_product_faq_and_reaches_live_capture():
    live = _LiveCapture()
    service = UniversalAwareConversationService(
        response_commands=_Commands(),
        base_conversation=_Base(),
        live_capture=live,
    )

    message = "55 inch Samsung Smart TV ఉంది ₹42000, new, delivery available"
    reply = service.process("seller-user", message)

    assert reply == "captured-new-offer"
    assert live.calls == [("seller-user", message)]


def test_current_product_question_still_uses_matched_faq_context():
    class SameContextCommands(_Commands):
        @staticmethod
        def _same_deal_context(request, message):
            return True

    service = UniversalAwareConversationService(
        response_commands=SameContextCommands(),
        base_conversation=_Base(),
    )

    reply = service._matched_product_faq("buyer-user", "available ఉందా?")

    assert "Gajakesari Punugu" in reply
    assert "available" in reply
