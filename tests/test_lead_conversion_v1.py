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


def _build(request, tmp_path):
    buyer = "919900000002"
    seller = "919900000001"
    contacts = {
        seller: {"mobile": seller, "name": "Seller"},
        buyer: {"mobile": buyer, "name": "Buyer"},
    }
    repository = UniversalNotificationRepository(str(tmp_path / f"lead-{request['id']}.db"))
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
    return buyer, seller, repository, whatsapp, notifications, commands


def _complete_flow(request, target_user_id, tmp_path):
    buyer, seller, repository, whatsapp, notifications, commands = _build(request, tmp_path)

    plan = {
        "waves": [{
            "wave": 1,
            "targets": [{"user_id": target_user_id, "distance_km": 1.2, "score": 0.95}],
        }]
    }
    result = notifications.dispatch_plan(request, plan)
    assert result["sent"] == 1

    # Buyer always receives the match choice, even when the original request is NEED.
    assert whatsapp.sent[-1]["to"] == buyer
    first_buttons = whatsapp.sent[-1]["buttons"]
    assert first_buttons[0]["id"] == f"BUY_INTERESTED {request['id']} {seller}"
    assert first_buttons[1]["id"] == f"BUY_NOT_INTERESTED {request['id']} {seller}"

    interest_reply = commands.process_text(buyer, f"BUY_INTERESTED {request['id']} {seller}")
    assert "seller" in interest_reply.lower()
    assert whatsapp.sent[-1]["to"] == seller
    assert whatsapp.sent[-1]["buttons"][0]["id"] == f"SELLER_CONFIRM {request['id']} {buyer}"

    seller_reply = commands.process_text(seller, f"SELLER_CONFIRM {request['id']} {buyer}")
    assert "Order Continue" in seller_reply
    assert whatsapp.sent[-1]["to"] == buyer
    buyer_choice_buttons = whatsapp.sent[-1]["buttons"]
    assert buyer_choice_buttons[0]["id"] == f"ORDER_CONTINUE {request['id']} {seller}"
    assert buyer_choice_buttons[1]["id"] == f"DIRECT_TALK {request['id']} {seller}"

    interest = repository.get_interest(request["id"], seller)
    assert interest["requester_user_id"] == buyer
    assert interest["responder_user_id"] == seller
    assert interest["requester_status"] == "ACCEPTED"
    assert interest["qualification_status"] == "READY_FOR_BUYER"

    order_reply = commands.process_text(buyer, f"ORDER_CONTINUE {request['id']} {seller}")
    assert "delivery address" in order_reply.lower()
    interest = repository.get_interest(request["id"], seller)
    assert interest["qualification_status"] == "WAITING_ADDRESS"

    buyer_reply = commands.process_text(buyer, "12 Main Road, Vuyyuru, Krishna District 521165")
    assert "qualified order lead" in buyer_reply.lower()
    interest = repository.get_interest(request["id"], seller)
    assert interest["qualification_status"] == "QUALIFIED"
    assert "Vuyyuru" in interest["delivery_address"]
    assert int(interest["contact_shared"]) == 0

    seller_cards = [item for item in whatsapp.sent if item["to"] == seller and "Qualified Order Lead" in item["body"]]
    assert len(seller_cards) == 1

    contact_reply = commands.process_text(buyer, f"DIRECT_TALK {request['id']} {seller}")
    assert "Seller contact" in contact_reply
    interest = repository.get_interest(request["id"], seller)
    assert int(interest["contact_shared"]) == 1


def test_need_owner_is_buyer_and_seller_never_gets_interest_button(tmp_path):
    buyer = "919900000002"
    seller = "919900000001"
    request = {
        "id": 51,
        "user_id": buyer,
        "side": "NEED",
        "status": "ACTIVE",
        "subject": "Gajakesari Punugu",
        "quantity": 1,
        "unit": "pack",
    }
    _complete_flow(request, seller, tmp_path)


def test_offer_owner_is_seller_and_target_buyer_still_gets_interest_button(tmp_path):
    buyer = "919900000002"
    seller = "919900000001"
    request = {
        "id": 52,
        "user_id": seller,
        "side": "OFFER",
        "status": "ACTIVE",
        "subject": "Gajakesari Punugu",
        "price": 99,
        "quantity": 1,
        "unit": "pack",
    }
    _complete_flow(request, buyer, tmp_path)
