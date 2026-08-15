from app.services.buyer_intelligence_service import BuyerIntelligenceService
from app.services.decision_opportunity_service import DecisionOpportunityService
from app.services.product_buyer_runtime_service import ProductBuyerRuntimeService
from app.services.universal_aware_conversation_service import UniversalAwareConversationService


class Notifications:
    def latest_interest_for_buyer(self, buyer):
        return {
            "request_id": 7,
            "responder_user_id": "seller-1",
            "requester_status": "ACCEPTED",
        }


class Demands:
    def get(self, request_id):
        return {"id": request_id, "domain": "PRODUCT", "subject": "Mixer Grinder"}


class Catalog:
    def find_active(self, seller_user_id, subject):
        return {
            "id": 11,
            "seller_user_id": seller_user_id,
            "subject": subject,
            "variant": "750W",
            "price": 2999,
            "stock_status": "IN_STOCK",
            "delivery_available": 1,
            "features": ["3 jars", "2 year motor warranty"],
        }


class Desk:
    def __init__(self, result):
        self.result = result

    def answer(self, product, question):
        return dict(self.result)


class Rag:
    def __init__(self, live_sensitive=False):
        self.live_sensitive = live_sensitive

    def retrieve_context(self, query, **kwargs):
        return {
            "status": "CONTEXT_FOUND",
            "live_verification_required": self.live_sensitive,
            "evidence": [{"content": "Seller confirmed motor warranty is 2 years."}],
        }


def runtime(desk_result, live_sensitive=False):
    return ProductBuyerRuntimeService(
        notification_repository=Notifications(),
        demand_repository=Demands(),
        catalog_repository=Catalog(),
        product_desk=Desk(desk_result),
        rag_service=Rag(live_sensitive=live_sensitive),
        buyer_intelligence=BuyerIntelligenceService(),
        decision_service=DecisionOpportunityService(),
    )


def test_stable_rag_evidence_prevents_unnecessary_seller_escalation():
    service = runtime({"status": "ASK_SELLER_ONCE", "answer": "Need seller confirmation"})
    reply = service.process("buyer-1", "motor warranty ఎంత?")
    assert reply == "Seller confirmed motor warranty is 2 years."


def test_live_sensitive_rag_never_overrides_fresh_desk_answer():
    service = runtime(
        {"status": "ASK_SELLER_ONCE", "answer": "Current price needs seller confirmation"},
        live_sensitive=True,
    )
    reply = service.process("buyer-1", "price ఎంత?")
    assert reply == "Current price needs seller confirmation"


def test_decision_question_runs_buyer_and_decision_layers():
    service = runtime({"status": "ANSWERED", "answer": "Seller confirmed details."})
    packet = service.evaluate("buyer-1", "ఈ mixer కొనాలా?")
    assert packet["buyer_guide"]["subject"] == "Mixer Grinder"
    assert packet["decision"]["goal"] == "BUY_SMART"
    reply = service.process("buyer-1", "ఈ mixer కొనాలా?")
    assert "PODX Buyer Intelligence" in reply
    assert "final fresh price & stock" in reply


class ResponseCommands:
    def process_text(self, **kwargs):
        return None


class ProductRuntime:
    def process(self, **kwargs):
        return "INTELLIGENT_PRODUCT_REPLY"


class BaseConversation:
    user_repository = None
    session_registry = None

    def process(self, **kwargs):
        return "BASE_REPLY"


def test_universal_conversation_routes_product_runtime_before_legacy_faq():
    service = UniversalAwareConversationService(
        response_commands=ResponseCommands(),
        base_conversation=BaseConversation(),
        product_runtime=ProductRuntime(),
    )
    assert service.process("buyer-1", "price ఎంత?") == "INTELLIGENT_PRODUCT_REPLY"
