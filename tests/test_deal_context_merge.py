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


def test_buyer_telugu_quantity_is_reused_in_seller_reply_and_total(tmp_path):
    repo = DealDiscussionRepository(str(tmp_path / "podx.db"))
    whatsapp = FakeWhatsApp()
    service = DealDiscussionService(repo, whatsapp, _contact)
    request = {
        "id": 77,
        "domain": "PRODUCT",
        "subject": "chicken",
        "quantity": None,
        "unit": None,
        "price": None,
    }

    repo.start(77, "buyer", "seller", {})
    repo.mark_waiting_buyer_change(77, "seller")

    buyer_reply = service.consume_buyer_change(
        request,
        "buyer",
        "seller",
        "5 కేజీలు కావాలి, మంచి క్వాలిటీ కావాలి. రేట్ ఎంత?",
    )

    assert "sellerకి పంపాను" in buyer_reply
    deal = repo.get(77, "seller")
    assert deal["details"]["quantity"] == 5.0
    assert deal["details"]["unit"] == "kg"

    seller_reply = service.consume_seller_text(
        request,
        "buyer",
        "seller",
        "₹220 per kg, fresh skinless chicken, today available, delivery చేస్తాను",
    )

    assert "Buyerకి summary" in seller_reply
    assert "quantity" not in seller_reply.lower()
    assert whatsapp.buttons
    summary = whatsapp.buttons[-1][1]
    assert "Quantity: 5 kg" in summary
    assert "Rate: ₹220 / kg" in summary
    assert "Total: ₹1,100" in summary
    assert "fresh" in summary
    assert "skinless" in summary
    assert "Fulfilment: delivery" in summary
    assert "Contact details ఇంకా private" in summary


def test_telugu_quantity_variants_parse_without_ascii_word_boundary(tmp_path):
    repo = DealDiscussionRepository(str(tmp_path / "podx.db"))
    service = DealDiscussionService(repo, FakeWhatsApp(), _contact)
    request = {"id": 1, "domain": "PRODUCT", "subject": "chicken", "quantity": None}

    for text in ("5 కేజీలు కావాలి", "5 కేజీ కావాలి", "5 కిలోలు కావాలి", "5 కిలో కావాలి"):
        parsed = service._parse_details(request, text)
        assert parsed["quantity"] == 5.0
        assert parsed["unit"] == "kg"
