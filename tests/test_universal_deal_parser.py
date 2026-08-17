from app.repositories.deal_discussion_repository import DealDiscussionRepository
from app.services.deal_discussion_service import DealDiscussionService


class FakeWhatsApp:
    def __init__(self):
        self.sent = []
        self.buttons = []

    def send_text_message(self, recipient_mobile, message):
        self.sent.append((str(recipient_mobile), str(message)))
        return {"success": True}

    def send_reply_buttons(self, recipient_mobile, body, buttons):
        self.buttons.append((str(recipient_mobile), str(body), buttons))
        return {"success": True}


def _contact(user_id):
    return {"mobile": str(user_id)}


def test_universal_product_message_captures_quantity_price_variant_and_pickup():
    service = DealDiscussionService(None, FakeWhatsApp(), _contact)
    request = {
        "id": 1,
        "domain": "PRODUCT",
        "subject": "rice bag",
        "quantity": None,
        "unit": None,
        "price": None,
    }

    parsed = service._parse_details(request, "5 kg rice bag 300rs only pickup sonarice")

    assert parsed["quantity"] == 5.0
    assert parsed["unit"] == "kg"
    assert parsed["rate"] == 300.0
    assert parsed["rate_unit"] == "bag"
    assert parsed["fulfilment"] == "pickup"
    assert "sonarice" in parsed["quality"]
    assert service._missing_required(request, parsed, "5 kg rice bag 300rs only pickup sonarice") == []


def test_product_parser_accepts_price_before_or_after_currency_marker():
    service = DealDiscussionService(None, FakeWhatsApp(), _contact)
    request = {"id": 2, "domain": "PRODUCT", "subject": "item", "quantity": 2, "unit": "piece"}

    assert service._parse_details(request, "Rs 450 delivery")["rate"] == 450.0
    assert service._parse_details(request, "450rs delivery")["rate"] == 450.0


def test_universal_product_does_not_require_optional_quality_field():
    service = DealDiscussionService(None, FakeWhatsApp(), _contact)
    request = {"id": 3, "domain": "PRODUCT", "subject": "water cans", "quantity": None, "price": None}
    parsed = service._parse_details(request, "2 cans 100rs delivery")

    # Quantity vocabulary can grow independently, but optional quality/type must never block a valid quick deal.
    parsed["quantity"] = 2.0
    parsed["unit"] = "piece"
    assert "quality/type" not in service._missing_required(request, parsed, "2 cans 100rs delivery")


def test_existing_chicken_flow_still_parses_per_kg_rate():
    service = DealDiscussionService(None, FakeWhatsApp(), _contact)
    request = {"id": 4, "domain": "PRODUCT", "subject": "fresh skinless chicken", "quantity": 5, "unit": "kg"}
    parsed = service._parse_details(request, "₹220 per kg, fresh skinless chicken, today available, delivery చేస్తాను")

    assert parsed["rate"] == 220.0
    assert parsed["rate_unit"] == "kg"
    assert parsed["fulfilment"] == "delivery"
    assert "fresh" in parsed["quality"]
