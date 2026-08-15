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
        self.sent.append({"type": "text", "to": str(recipient_mobile), "body": str(message), "buttons": None})
        return {"success": True, "provider_message_id": f"m{len(self.sent)}"}

    def send_reply_buttons(self, recipient_mobile, body, buttons):
        self.sent.append({"type": "buttons", "to": str(recipient_mobile), "body": str(body), "buttons": list(buttons)})
        return {"success": True, "provider_message_id": f"m{len(self.sent)}"}

    def send_image_by_id(self, recipient_mobile, media_id, caption=""):
        self.sent.append({"type": "image", "to": str(recipient_mobile), "media_id": media_id, "body": caption, "buttons": None})
        return {"success": True, "provider_message_id": f"m{len(self.sent)}"}


def _build(request, tmp_path):
    buyer, seller = "919900000002", "919900000001"
    contacts = {
        seller: {"mobile": seller, "name": "Seller"},
        buyer: {"mobile": buyer, "name": "Buyer"},
    }
    repo = UniversalNotificationRepository(str(tmp_path / f"lead-{request['id']}.db"))
    wa = FakeWhatsApp()
    notifications = UniversalNotificationService(repo, wa, lambda uid: contacts.get(str(uid)))
    commands = UniversalResponseCommandService(FakeDemandRepository(request), notifications, repo)
    return buyer, seller, repo, wa, notifications, commands


def _offer_request(request_id=52, price=99):
    return {
        "id": request_id,
        "user_id": "919900000001",
        "side": "OFFER",
        "status": "ACTIVE",
        "subject": "Gajakesari Punugu",
        "price": price,
        "quantity": 1,
        "unit": "pack",
        "media_ref": "media-product-1",
    }


def test_final_confirm_is_required_before_conversion(tmp_path):
    request = _offer_request()
    buyer, seller, repo, wa, notifications, commands = _build(request, tmp_path)

    notifications.dispatch_plan(request, {"waves": [{"wave": 1, "targets": [{"user_id": buyer, "distance_km": 1.2, "score": .95}]}]})
    commands.process_text(buyer, f"BUY_INTERESTED 52 {seller}")
    commands.process_text(seller, f"SELLER_CONFIRM 52 {buyer}")
    commands.process_text(buyer, f"ORDER_CONTINUE 52 {seller}")

    reply = commands.process_text(buyer, "12 Main Road, Vuyyuru, Krishna District 521165")
    assert "Final Order Summary" in reply
    interest = repo.get_interest(52, seller)
    assert interest["qualification_status"] == "WAITING_FINAL_CONFIRM"
    assert interest["converted_at"] is None
    assert not any("New Confirmed Order" in item["body"] for item in wa.sent)

    final_reply = commands.process_text(buyer, f"FINAL_CONFIRM 52 {seller}")
    assert "Order Confirmed" in final_reply
    interest = repo.get_interest(52, seller)
    assert interest["qualification_status"] == "CONVERTED"
    assert interest["converted_at"] is not None
    seller_cards = [item for item in wa.sent if item["to"] == seller and "New Confirmed Order" in item["body"]]
    assert len(seller_cards) == 1
    assert "Price: ₹99" in seller_cards[0]["body"]


def test_final_cancel_never_converts(tmp_path):
    request = _offer_request(request_id=53)
    buyer, seller, repo, wa, notifications, commands = _build(request, tmp_path)
    repo.record_interest(53, buyer, seller)
    repo.set_seller_decision(53, seller, True)
    repo.mark_waiting_address(53, seller)
    repo.save_delivery_address(53, seller, "12 Main Road, Vuyyuru 521165")

    reply = commands.process_text(buyer, f"FINAL_CANCEL 53 {seller}")
    assert "cancel" in reply.lower()
    interest = repo.get_interest(53, seller)
    assert interest["qualification_status"] == "CANCELLED"
    assert interest["converted_at"] is None
    assert not any("New Confirmed Order" in item["body"] for item in wa.sent)


def test_offer_without_price_is_blocked_before_address(tmp_path):
    request = _offer_request(request_id=54, price=None)
    buyer, seller, repo, wa, notifications, commands = _build(request, tmp_path)
    repo.record_interest(54, buyer, seller)
    repo.set_seller_decision(54, seller, True)
    reply = commands.process_text(buyer, f"ORDER_CONTINUE 54 {seller}")
    assert "price" in reply.lower()
    assert repo.get_interest(54, seller)["qualification_status"] == "READY_FOR_BUYER"


def test_need_price_is_labelled_budget_not_seller_price(tmp_path):
    request = {
        "id": 55,
        "user_id": "919900000002",
        "side": "NEED",
        "status": "ACTIVE",
        "subject": "Rice",
        "price": 1000,
        "quantity": 1,
        "unit": "bag",
        "media_ref": "m3",
    }
    buyer, seller, repo, wa, notifications, commands = _build(request, tmp_path)
    notifications.dispatch_plan(request, {"waves": [{"wave": 1, "targets": [{"user_id": seller, "distance_km": 2, "score": .9}]}]})
    assert "మీ budget: ₹1,000" in wa.sent[-1]["body"]
    assert "Price: ₹1,000" not in wa.sent[-1]["body"]
