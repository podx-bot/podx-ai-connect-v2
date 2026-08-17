from app.services.product_buyer_runtime_service import ProductBuyerRuntimeService
from app.services.universal_context_router import UniversalContextRouter


class _Notifications:
    @staticmethod
    def latest_interest_for_buyer(_sender):
        return {"request_id": 1, "responder_user_id": "seller-1", "requester_status": "ACCEPTED"}


class _Demands:
    @staticmethod
    def get(_request_id):
        return {"id": 1, "domain": "PRODUCT", "subject": "Gajakesari Punugu"}


class _Catalog:
    def __init__(self):
        self.called = False

    def find_active(self, _seller, _subject):
        self.called = True
        return {"id": 10, "subject": "Gajakesari Punugu"}


def test_new_product_message_bypasses_old_product_runtime_context():
    service = ProductBuyerRuntimeService.__new__(ProductBuyerRuntimeService)
    service.notifications = _Notifications()
    service.demands = _Demands()
    service.catalog = _Catalog()
    service.context_router = UniversalContextRouter()

    result = service.evaluate(
        "buyer-1",
        "55 inch Samsung smart TV ఉంది ₹42000, new, delivery available",
    )

    assert result is None
    assert service.catalog.called is False
