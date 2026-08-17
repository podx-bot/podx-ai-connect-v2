from app.services.universal_context_router import UniversalContextRouter


def test_new_product_message_is_not_same_as_old_product_context():
    router = UniversalContextRouter()
    old_request = {"domain": "PRODUCT", "subject": "Gajakesari Punugu"}
    message = "55 inch Samsung smart TV ఉంది ₹42000, new, delivery available"

    assert router.should_consume_as_deal_followup(old_request, message) is False
