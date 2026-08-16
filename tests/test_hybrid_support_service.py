from app.repositories.hybrid_support_repository import HybridSupportRepository
from app.repositories.rag_knowledge_repository import RagKnowledgeRepository
from app.services.hybrid_support_service import HybridSupportService


class FakeWhatsApp:
    def __init__(self): self.sent=[]
    def send_text_message(self, mobile, message):
        self.sent.append((str(mobile), str(message)))
        return {"success": True}


def resolver(user_id):
    return {"mobile": str(user_id), "name": "User"}


def test_unresolved_question_creates_one_ticket_and_notifies_admin(tmp_path):
    db=str(tmp_path/'support.db'); wa=FakeWhatsApp()
    service=HybridSupportService(HybridSupportRepository(db),RagKnowledgeRepository(db),wa,resolver,admin_mobile='919999999999')
    first=service.process('918888888888','PODXలో ఈ option ఎలా పని చేస్తుంది?')
    second=service.process('918888888888','PODXలో ఈ option ఎలా పని చేస్తుంది?')
    assert 'Ticket #1' in first
    assert 'already' in second or 'ఇప్పటికే' in second
    assert len(wa.sent)==1
    assert wa.sent[0][0]=='919999999999'
    assert 'ADMIN ANSWER 1' in wa.sent[0][1]


def test_admin_answer_notifies_user_and_becomes_future_knowledge(tmp_path):
    db=str(tmp_path/'support2.db'); wa=FakeWhatsApp(); repo=HybridSupportRepository(db); rag=RagKnowledgeRepository(db)
    service=HybridSupportService(repo,rag,wa,resolver,admin_mobile='919999999999')
    service.process('918888888888','PODX support timing ఏమిటి?')
    reply=service.process('919999999999','ADMIN ANSWER 1 | PODX support 9 AM నుంచి 6 PM వరకు available.')
    assert 'resolve' in reply
    ticket=repo.get(1); assert ticket['status']=='ANSWERED'; assert ticket['knowledge_id'] is not None
    assert any(mobile=='918888888888' and '9 AM' in message for mobile,message in wa.sent)
    learned=service.process('917777777777','PODX support timing ఏమిటి?')
    assert learned.startswith('🤖')
    assert '9 AM' in learned


def test_non_admin_cannot_answer_when_admin_is_configured(tmp_path):
    db=str(tmp_path/'support3.db'); wa=FakeWhatsApp()
    service=HybridSupportService(HybridSupportRepository(db),RagKnowledgeRepository(db),wa,resolver,admin_mobile='919999999999')
    service.process('918888888888','ఈ feature ఎందుకు కనిపించడం లేదు?')
    reply=service.process('917777777777','ADMIN ANSWER 1 | test')
    assert 'admin' in reply.casefold()


def test_non_question_does_not_hijack_normal_flow(tmp_path):
    db=str(tmp_path/'support4.db'); wa=FakeWhatsApp()
    service=HybridSupportService(HybridSupportRepository(db),RagKnowledgeRepository(db),wa,resolver,admin_mobile='919999999999')
    assert service.process('918888888888','చికెన్ 5 కేజీలు కావాలి') is None
