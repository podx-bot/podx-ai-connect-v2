from app.services.universal_response_command_service import UniversalResponseCommandService


class _Demands:
    def get(self, request_id):
        return {"id": request_id, "status": "ACTIVE", "user_id": "buyer", "side": "NEED", "subject": "chicken"}


class _Notifications:
    @staticmethod
    def resolve_roles(request, opposite):
        return str(request["user_id"]), str(opposite)

    def __init__(self, status):
        self.status = status

    def register_interest(self, request, buyer, seller):
        return {"status": self.status, "notification": {"success": self.status == "WAITING_SELLER_CONFIRM"}}


class _Repo:
    db_path = ":memory:"


def test_buyer_is_not_told_seller_was_notified_when_delivery_failed():
    service = UniversalResponseCommandService(_Demands(), _Notifications("SELLER_NOTIFICATION_FAILED"), _Repo())
    service.deals = None
    reply = service._buyer_interest("buyer", 9, "seller")
    assert "delivery" in reply.lower() or "పంపలేకపోయాను" in reply
    assert "sellerకి పంపాను" not in reply
