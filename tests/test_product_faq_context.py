from app.repositories.universal_notification_repository import UniversalNotificationRepository
from app.services.universal_aware_conversation_service import UniversalAwareConversationService


class FakeDemands:
    def __init__(self, request):
        self.request = dict(request)

    def get(self, request_id):
        return dict(self.request) if int(request_id) == int(self.request['id']) else None


class FakeCommands:
    def __init__(self, repo, request):
        self.notification_repository = repo
        self.demands = FakeDemands(request)

    def process_text(self, sender_mobile, message):
        return None


class FakeBase:
    user_repository = None
    session_registry = None

    def process(self, sender_mobile, message):
        return 'BASE'


class FakeLive:
    def process_text(self, sender_mobile, message):
        return 'CAPTURED_AS_NEW_REQUEST'


def build_service(tmp_path, request, seller_status='PENDING'):
    buyer = '919900000002'
    seller = '919900000001'
    repo = UniversalNotificationRepository(str(tmp_path / 'faq.db'))
    repo.record_interest(request['id'], buyer, seller)
    if seller_status == 'ACCEPTED':
        repo.set_seller_decision(request['id'], seller, True)
    commands = FakeCommands(repo, request)
    return buyer, UniversalAwareConversationService(commands, FakeBase(), live_capture=FakeLive())


def test_price_question_stays_in_product_context(tmp_path):
    request = {'id': 71, 'user_id': '919900000001', 'side': 'OFFER', 'domain': 'PRODUCT', 'subject': 'Gajakesari Punugu', 'price': 99}
    buyer, service = build_service(tmp_path, request)
    reply = service.process(buyer, 'దీని ధర ఎంత?')
    assert '₹99' in reply
    assert reply != 'CAPTURED_AS_NEW_REQUEST'


def test_need_origin_does_not_invent_seller_price(tmp_path):
    request = {'id': 72, 'user_id': '919900000002', 'side': 'NEED', 'domain': 'PRODUCT', 'subject': 'Gajakesari Punugu'}
    buyer, service = build_service(tmp_path, request)
    reply = service.process(buyer, 'price ఎంత')
    assert 'final price ఇంకా confirm కాలేదు' in reply
    assert reply != 'CAPTURED_AS_NEW_REQUEST'


def test_availability_uses_seller_confirmation(tmp_path):
    request = {'id': 73, 'user_id': '919900000001', 'side': 'OFFER', 'domain': 'PRODUCT', 'subject': 'Gajakesari Punugu', 'price': 99}
    buyer, service = build_service(tmp_path, request, seller_status='ACCEPTED')
    reply = service.process(buyer, 'stock ఉందా?')
    assert 'available అని confirm చేశారు' in reply
    assert reply != 'CAPTURED_AS_NEW_REQUEST'
