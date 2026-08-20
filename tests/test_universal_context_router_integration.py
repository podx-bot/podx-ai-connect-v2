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
        return {"success": True}

    def send_reply_buttons(self, recipient_mobile, body, buttons):
        self.buttons.append((str(recipient_mobile), str(body), buttons))
        return {"success": True}


def _contact(user_id):
    return {"mobile": str(user_id), "phone": str(user_id), "name": str(user_id).title()}


def _build_pending_chicken_deal(tmp_path):
    db = str(tmp_path / "podx.db")
    demands = UniversalDemandRepository(db)
    notifications_repo = UniversalNotificationRepository(db)
    whatsapp = FakeWhatsApp()
    notifications = UniversalNotificationService(notifications_repo, whatsapp, _contact)
    commands = UniversalResponseCommandService(demands, notifications, notifications_repo)
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
    notifications_repo.record_interest(request_id, "buyer", "seller")
    commands.process_text("seller", f"SELLER_CONFIRM {request_id} buyer")
    return demands, notifications_repo, whatsapp, commands, request_id


def test_new_subject_bypasses_old_pending_deal(tmp_path):
    _, _, whatsapp, commands, _ = _build_pending_chicken_deal(tmp_path)

    reply = commands.process_text("seller", "5 kg rice bag 300rs only pickup sonarice")

    # Returning None deliberately hands the message to UniversalLiveCaptureService,
    # which can create a fresh request instead of mutating the chicken deal.
    assert reply is None
    assert not whatsapp.buttons


def test_telugu_new_subject_bypasses_old_pending_deal(tmp_path):
    _, _, whatsapp, commands, _ = _build_pending_chicken_deal(tmp_path)

    reply = commands.process_text("seller", "నాకు 25 కేజీల బాస్మతి రైస్ కావాలి")

    # This is the production regression: the old chicken state must not consume
    # an explicit new rice request. None means routing can continue to live capture.
    assert reply is None
    assert not whatsapp.buttons


def test_attribute_only_reply_still_updates_current_deal(tmp_path):
    _, _, whatsapp, commands, _ = _build_pending_chicken_deal(tmp_path)

    reply = commands.process_text("seller", "₹220 per kg fresh skinless chicken today delivery")

    assert "Buyerకి summary" in reply
    assert whatsapp.buttons
    summary = whatsapp.buttons[-1][1]
    assert "Item: chicken" in summary
    assert "Rate: ₹220 / kg" in summary
