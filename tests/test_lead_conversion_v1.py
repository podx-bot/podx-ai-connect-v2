from app.repositories.universal_notification_repository import UniversalNotificationRepository
from app.services.universal_notification_service import UniversalNotificationService
from app.services.universal_response_command_service import UniversalResponseCommandService


class FakeDemandRepository:
    def __init__(self, request):
        self.request = dict(request)

    def get(self, request_id):
        return dict(self.request) if int(request_id) == int(self.request["id"]) else None


class FakeWhatsApp:
    def __init__(self):
        self.sent = []

    def send_text_message(self, recipient_mobile, message):
        self.sent.append({"to": str(recipient_mobile), "body": str(message), "buttons": None})
        return {"success": True, "provider_message_id": f"m{len(self.sent)}"}

    def send_reply_buttons(self, recipient_mobile, body, buttons):
        self.sent.append({"to": str(recipient_mobile), "body": str(body), "buttons": list(buttons)})
        return {"success": True, "provider_message_id": f"m{len(self.sent)}"}


def test_seller_confirms_once_then_podx_qualifies_buyer(tmp_path):
    seller = "919900000001"
    buyer = "919900000002"
    request = {
        "id": 5,
        "user_id": seller,
        "status": "ACTIVE",
        "subject": "Gajakesari Punugu",
        "price": 99,
        "quantity": 1,
        "unit": "pack",
    }

    repository = UniversalNotificationRepository(str(tmp_path / "lead.db"))
    notification_id = repository.reserve_notification(5, seller, buyer)
    repository.mark_sent(notification_id, "wamid-test")

    contacts = {
        seller: {"mobile": seller, "name": "Seller"},
        buyer: {"mobile": buyer, "name": "Buyer"},
    }
    whatsapp = FakeWhatsApp()
    notifications = UniversalNotificationService(
        notification_repository=repository,
        whatsapp_service=whatsapp,
        contact_resolver=lambda user_id: contacts.get(str(user_id)),
    )
    commands = UniversalResponseCommandService(
        demand_repository=FakeDemandRepository(request),
        notification_service=notifications,
        notification_repository=repository,
    )

    interest_reply = commands.process_text(buyer, "INTERESTED 5")
    assert "Seller confirm" in interest_reply
    assert whatsapp.sent[-1]["to"] == seller
    assert whatsapp.sent[-1]["buttons"][0]["id"] == "CONFIRM 5"

    seller_reply = commands.process_text(seller, "CONFIRM 5")
    assert "buyer delivery details" in seller_reply
    assert whatsapp.sent[-1]["to"] == buyer
    assert "Delivery" in whatsapp.sent[-1]["body"]

    interest = repository.get_interest(5, buyer)
    assert interest["requester_status"] == "ACCEPTED"
    assert interest["qualification_status"] == "WAITING_ADDRESS"
    assert int(interest["contact_shared"]) == 0

    buyer_reply = commands.process_text(buyer, "12 Main Road, Vuyyuru, Krishna District 521165")
    assert "qualified lead" in buyer_reply.lower()
    interest = repository.get_interest(5, buyer)
    assert interest["qualification_status"] == "QUALIFIED"
    assert "Vuyyuru" in interest["delivery_address"]
    assert int(interest["contact_shared"]) == 0

    seller_cards = [item for item in whatsapp.sent if item["to"] == seller and "Qualified Lead" in item["body"]]
    assert len(seller_cards) == 1
    buyer_buttons = [item for item in whatsapp.sent if item["to"] == buyer and item["buttons"]]
    assert any(button["id"] == "CONTACT 5" for item in buyer_buttons for button in item["buttons"])

    contact_reply = commands.process_text(buyer, "CONTACT 5")
    assert "Seller contact" in contact_reply
    interest = repository.get_interest(5, buyer)
    assert int(interest["contact_shared"]) == 1
