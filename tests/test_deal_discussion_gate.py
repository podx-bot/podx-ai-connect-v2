from app.repositories.universal_demand_repository import UniversalDemandRepository
from app.repositories.universal_notification_repository import UniversalNotificationRepository
from app.services.universal_notification_service import UniversalNotificationService
from app.services.universal_response_command_service import UniversalResponseCommandService


class FakeWhatsApp:
    def __init__(self):
        self.sent = []
        self.buttons = []

    def send_text_message(self, recipient_mobile, message):
        self.sent.append((str(recipient_mobile), str(message)))
        return {"success": True, "provider_message_id": f"m-{len(self.sent)}"}

    def send_reply_buttons(self, recipient_mobile, body, buttons):
        self.buttons.append((str(recipient_mobile), str(body), buttons))
        return {"success": True, "provider_message_id": f"b-{len(self.buttons)}"}


def _contact(user_id):
    return {"mobile": str(user_id), "phone": str(user_id), "name": str(user_id).title()}


def _build(tmp_path):
    db = str(tmp_path / "podx.db")
    demands = UniversalDemandRepository(db)
    repo = UniversalNotificationRepository(db)
    whatsapp = FakeWhatsApp()
    notifications = UniversalNotificationService(repo, whatsapp, _contact)
    commands = UniversalResponseCommandService(demands, notifications, repo)
    request_id = demands.create(
        {
            "user_id": "buyer",
            "side": "NEED",
            "domain": "PRODUCT",
            "subject": "chicken",
            "quantity": 5,
            "unit": "kg",
        }
    )
    repo.record_interest(request_id, "buyer", "seller")
    return demands, repo, whatsapp, commands, request_id


def test_seller_confirm_starts_deal_discussion_not_order_or_contact(tmp_path):
    _, _, whatsapp, commands, request_id = _build(tmp_path)

    reply = commands.process_text("seller", f"SELLER_CONFIRM {request_id} buyer")

    assert "deal details" in reply.lower()
    assert any(to == "buyer" and "Contact details" in msg for to, msg in whatsapp.sent)
    assert any(to == "seller" and "Deal Discussion" in msg for to, msg in whatsapp.sent)
    assert not any("Order Continue" in body or "Direct Talk" in body for _, body, _ in whatsapp.buttons)


def test_existing_quantity_is_reused_and_missing_fields_are_requested(tmp_path):
    _, _, _, commands, request_id = _build(tmp_path)
    commands.process_text("seller", f"SELLER_CONFIRM {request_id} buyer")

    reply = commands.process_text("seller", "fresh chicken available today")

    assert "rate/unit" in reply
    assert "quantity" not in reply.lower()


def test_complete_seller_details_produce_private_deal_summary(tmp_path):
    _, _, whatsapp, commands, request_id = _build(tmp_path)
    commands.process_text("seller", f"SELLER_CONFIRM {request_id} buyer")

    reply = commands.process_text("seller", "₹220 per kg fresh skinless available today delivery")

    assert "Buyerకి summary" in reply
    buyer_cards = [x for x in whatsapp.buttons if x[0] == "buyer"]
    assert buyer_cards
    body = buyer_cards[-1][1]
    assert "PODX Deal Summary" in body
    assert "Quantity: 5" in body
    assert "Rate: ₹220" in body
    assert "Phone: buyer" not in body
    assert "Phone: seller" not in body
    ids = [b["id"] for b in buyer_cards[-1][2]]
    assert f"DEAL_CONFIRM {request_id} seller" in ids
    assert f"DEAL_CHANGE {request_id} seller" in ids


def test_contact_and_order_are_blocked_before_deal_ok(tmp_path):
    _, _, whatsapp, commands, request_id = _build(tmp_path)
    commands.process_text("seller", f"SELLER_CONFIRM {request_id} buyer")
    commands.process_text("seller", "₹220 per kg fresh available today delivery")

    direct = commands.process_text("buyer", f"DIRECT_TALK {request_id} seller")
    order = commands.process_text("buyer", f"ORDER_CONTINUE {request_id} seller")

    assert "Deal Discussion" in direct
    assert "deal discussion" in order.lower()
    assert not any("Phone:" in msg for _, msg in whatsapp.sent)


def test_buyer_change_is_relayed_and_seller_revision_returns_updated_summary(tmp_path):
    _, _, whatsapp, commands, request_id = _build(tmp_path)
    commands.process_text("seller", f"SELLER_CONFIRM {request_id} buyer")
    commands.process_text("seller", "₹220 per kg fresh available today delivery")

    prompt = commands.process_text("buyer", f"DEAL_CHANGE {request_id} seller")
    assert "ఏ detail మార్చాలి" in prompt
    buyer_reply = commands.process_text("buyer", "rate 210 చేయండి, skinless కావాలి")
    assert "sellerకి పంపాను" in buyer_reply
    assert any(to == "seller" and "rate 210" in msg for to, msg in whatsapp.sent)

    seller_reply = commands.process_text("seller", "₹210 per kg fresh skinless available today delivery")
    assert "Buyerకి summary" in seller_reply
    body = [body for to, body, _ in whatsapp.buttons if to == "buyer"][-1]
    assert "Rate: ₹210" in body
    assert "Buyer clarification" in body


def test_deal_ok_unlocks_next_options_then_direct_talk_shares_contacts(tmp_path):
    _, _, whatsapp, commands, request_id = _build(tmp_path)
    commands.process_text("seller", f"SELLER_CONFIRM {request_id} buyer")
    commands.process_text("seller", "₹220 per kg fresh skinless available today delivery")

    confirm = commands.process_text("buyer", f"DEAL_CONFIRM {request_id} seller")
    assert "Deal confirm" in confirm
    buyer_cards = [x for x in whatsapp.buttons if x[0] == "buyer"]
    next_ids = [b["id"] for b in buyer_cards[-1][2]]
    assert f"ORDER_CONTINUE {request_id} seller" in next_ids
    assert f"DIRECT_TALK {request_id} seller" in next_ids

    direct = commands.process_text("buyer", f"DIRECT_TALK {request_id} seller")
    assert "Seller contact" in direct
    assert any(to == "buyer" and "Phone: seller" in msg for to, msg in whatsapp.sent)
    assert any(to == "seller" and "Phone: buyer" in msg for to, msg in whatsapp.sent)
