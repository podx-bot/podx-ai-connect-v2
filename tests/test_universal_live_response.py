from app.repositories.universal_demand_repository import UniversalDemandRepository
from app.repositories.universal_notification_repository import UniversalNotificationRepository
from app.services.universal_aware_conversation_service import UniversalAwareConversationService
from app.services.universal_notification_service import UniversalNotificationService
from app.services.universal_response_command_service import UniversalResponseCommandService


class FakeWhatsApp:
    def __init__(self):
        self.sent = []

    def send_text_message(self, recipient_mobile, message):
        self.sent.append((str(recipient_mobile), str(message)))
        return {"success": True, "provider_message_id": f"m-{len(self.sent)}"}


class BaseConversation:
    def process(self, sender_mobile, message):
        return f"BASE:{message}"


def _contact(user_id):
    names = {"buyer": "Buyer", "seller": "Seller"}
    return {"mobile": user_id, "phone": user_id, "name": names.get(user_id, "User")}


def _build(tmp_path):
    db = str(tmp_path / "podx.db")
    demands = UniversalDemandRepository(db)
    repo = UniversalNotificationRepository(db)
    whatsapp = FakeWhatsApp()
    notifications = UniversalNotificationService(repo, whatsapp, _contact)
    commands = UniversalResponseCommandService(demands, notifications, repo)
    live = UniversalAwareConversationService(commands, BaseConversation())
    return demands, repo, whatsapp, live


def test_natural_interest_then_natural_consent_shares_contacts(tmp_path):
    demands, repo, whatsapp, live = _build(tmp_path)
    request_id = demands.create({
        "user_id": "buyer",
        "side": "NEED",
        "domain": "PRODUCT",
        "subject": "sona masoori rice",
    })
    notification_id = repo.reserve_notification(request_id, "buyer", "seller")
    repo.mark_sent(notification_id, "provider-1")

    reply = live.process("seller", "ఇస్తాను")
    assert "interest" in reply.lower()
    assert any(to == "buyer" and "interested" in msg.lower() for to, msg in whatsapp.sent)
    consent_prompt = [msg for to, msg in whatsapp.sent if to == "buyer"][-1]
    assert "CONFIRM" in consent_prompt
    assert "seller" not in consent_prompt

    reply = live.process("buyer", "సరే")
    assert "contact details share" in reply
    assert any(to == "buyer" and "Phone: seller" in msg for to, msg in whatsapp.sent)
    assert any(to == "seller" and "Phone: buyer" in msg for to, msg in whatsapp.sent)


def test_explicit_interest_requires_targeted_notification(tmp_path):
    demands, repo, whatsapp, live = _build(tmp_path)
    request_id = demands.create({
        "user_id": "buyer",
        "side": "NEED",
        "domain": "SERVICE",
        "subject": "electrician",
    })
    reply = live.process("random-user", f"INTERESTED {request_id}")
    assert "notification" in reply
    assert not whatsapp.sent


def test_unrelated_text_falls_back_to_existing_conversation(tmp_path):
    _, _, _, live = _build(tmp_path)
    assert live.process("buyer", "hello podx") == "BASE:hello podx"
