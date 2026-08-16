from app.repositories.business_customer_desk_repository import BusinessCustomerDeskRepository
from app.repositories.rag_knowledge_repository import RagKnowledgeRepository
from app.services.business_customer_desk_service import BusinessCustomerDeskService


class FakeWhatsApp:
    def __init__(self):
        self.sent=[]
    def send_text_message(self, recipient_mobile, message):
        self.sent.append((str(recipient_mobile), str(message)))
        return {"success": True}


class FakeUsers:
    def __init__(self, registered=None):
        self.registered=set(registered or [])
    def find_by_whatsapp_mobile(self, mobile):
        return {"whatsapp_mobile": str(mobile), "registration_complete": 1 if str(mobile) in self.registered else 0}


def build(tmp_path):
    db=str(tmp_path/'desk.db')
    whatsapp=FakeWhatsApp()
    service=BusinessCustomerDeskService(
        BusinessCustomerDeskRepository(db),
        RagKnowledgeRepository(db),
        whatsapp,
        FakeUsers({'owner'}),
    )
    return service, whatsapp


def test_unknown_question_owner_teaches_once_then_future_auto_answers(tmp_path):
    service, whatsapp=build(tmp_path)
    setup=service.process_text('owner','BUSINESS ON Sai Restaurant | Restaurant')
    assert 'Business Desk ON' in setup
    code=setup.split('Code: ')[1].split('\n')[0].strip()

    first=service.process_text('customer1',f'ASK {code} What time do you close?')
    assert 'Ownerని ఒక్కసారి అడిగాను' in first
    owner_messages=[m for r,m in whatsapp.sent if r=='owner']
    assert len(owner_messages)==1
    assert 'What time do you close?' in owner_messages[0]

    duplicate=service.process_text('customer1',f'ASK {code} What time do you close?')
    assert 'ఇప్పటికే పంపాం' in duplicate
    assert len([m for r,m in whatsapp.sent if r=='owner'])==1

    qid=int(owner_messages[0].split('Question #')[1].split('\n')[0])
    resolved=service.process_text('owner',f'BIZ ANSWER {qid} | We close at 10 PM')
    assert 'knowledgeలో save' in resolved
    assert any(r=='customer1' and 'We close at 10 PM' in m for r,m in whatsapp.sent)

    future=service.process_text('customer2',f'PODX {code} What time do you close?')
    assert 'We close at 10 PM' in future
    assert 'Owner-confirmed PODX answer' in future
    assert len([m for r,m in whatsapp.sent if r=='owner'])==1


def test_wrong_owner_cannot_answer_and_desk_off_blocks_customer(tmp_path):
    service, whatsapp=build(tmp_path)
    setup=service.process_text('owner','BUSINESS ON Fresh Mart | Grocery')
    code=setup.split('Code: ')[1].split('\n')[0].strip()
    service.process_text('customer',f'ASK {code} Is milk available?')
    owner_message=[m for r,m in whatsapp.sent if r=='owner'][0]
    qid=int(owner_message.split('Question #')[1].split('\n')[0])
    denied=service.process_text('other',f'BIZ ANSWER {qid} | yes')
    assert 'మీ Business Deskకి చెందినది కాదు' in denied
    assert 'Business Desk OFF' in service.process_text('owner','BUSINESS OFF')
    assert 'activeగా లేదు' in service.process_text('customer',f'ASK {code} Is milk available?')


def test_unregistered_owner_cannot_enable(tmp_path):
    db=str(tmp_path/'desk2.db')
    service=BusinessCustomerDeskService(
        BusinessCustomerDeskRepository(db), RagKnowledgeRepository(db), FakeWhatsApp(), FakeUsers()
    )
    assert 'registration complete' in service.process_text('owner','BUSINESS ON Test Shop | Grocery')
