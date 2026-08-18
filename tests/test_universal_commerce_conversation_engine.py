from app.services.universal_commerce_conversation_engine import UniversalCommerceConversationEngine


class FakeDeals:
    def __init__(self, buyer_change=None, seller=None, buyer_summary=None):
        self.buyer_change = buyer_change
        self.seller = seller
        self.buyer_summary = buyer_summary

    def pending_for_buyer_change(self, sender):
        return self.buyer_change

    def pending_for_seller(self, sender):
        return self.seller

    def pending_for_buyer_summary(self, sender):
        return self.buyer_summary


class FakeNotifications:
    def __init__(self, final=None):
        self.final = final

    def latest_waiting_final_confirm_for_buyer(self, sender):
        return self.final


def test_final_confirm_tv_question_auto_routes_to_doubt_without_button():
    engine = UniversalCommerceConversationEngine()
    final = {"request_id": 10, "requester_user_id": "buyer", "responder_user_id": "seller"}
    decision = engine.decide(
        "buyer",
        "ఈ TVకి warranty ఉందా? installation freeనా?",
        deals=FakeDeals(),
        notifications=FakeNotifications(final),
    )
    assert decision.intent == "AUTO_BUYER_DOUBT"
    assert decision.request_id == 10
    assert decision.seller_user_id == "seller"


def test_explicit_buyer_doubt_state_wins_over_same_users_seller_state():
    engine = UniversalCommerceConversationEngine()
    deals = FakeDeals(
        buyer_change={"request_id": 20, "buyer_user_id": "same", "seller_user_id": "tv-seller"},
        seller={"request_id": 21, "buyer_user_id": "rice-buyer", "seller_user_id": "same"},
    )
    decision = engine.decide("same", "warranty ఉందా?", deals=deals, notifications=FakeNotifications())
    assert decision.intent == "BUYER_DOUBT_OR_CHANGE"
    assert decision.request_id == 20


def test_rice_seller_fact_reply_is_not_forced_into_question_flow():
    engine = UniversalCommerceConversationEngine()
    deals = FakeDeals(seller={"request_id": 30, "buyer_user_id": "b", "seller_user_id": "s", "status": "WAITING_SELLER_DETAILS"})
    decision = engine.decide("s", "5 kg sona rice bag ₹300 pickup available", deals=deals)
    assert decision.intent == "SELLER_DETAILS"


def test_live_warranty_reply_routes_to_buyer_clarification_before_missing_fields():
    engine = UniversalCommerceConversationEngine()
    deals = FakeDeals(
        seller={
            "request_id": 31,
            "buyer_user_id": "buyer",
            "seller_user_id": "seller",
            "status": "WAITING_SELLER_REVISION",
        }
    )
    decision = engine.decide("seller", "1 year warranty ఉంది", deals=deals)
    assert decision.intent == "SELLER_CLARIFICATION_REPLY"
    assert decision.request_id == 31
    assert decision.recommended_action == "ROUTE_TO_COUNTERPARTY"


def test_seller_counter_question_routes_back_to_buyer_privately():
    engine = UniversalCommerceConversationEngine()
    deals = FakeDeals(
        seller={
            "request_id": 32,
            "buyer_user_id": "buyer",
            "seller_user_id": "seller",
            "status": "WAITING_SELLER_REVISION",
        }
    )
    decision = engine.decide("seller", "ఏ color కావాలి?", deals=deals)
    assert decision.intent == "SELLER_COUNTER_QUESTION"


def test_cement_question_is_generic_question_not_unit_validation():
    engine = UniversalCommerceConversationEngine()
    decision = engine.decide("buyer", "ఈ cement ఏ grade? manufacturing date ఏంటి?")
    assert decision.intent == "GENERIC_COMMERCE_QUESTION"


def test_medicine_question_is_generic_question_not_forced_quantity():
    engine = UniversalCommerceConversationEngine()
    decision = engine.decide("buyer", "ఈ medicine expiry ఎప్పుడు? stripలో ఎన్ని tablets ఉన్నాయి?")
    assert decision.intent == "GENERIC_COMMERCE_QUESTION"


def test_service_question_uses_same_universal_question_intent():
    engine = UniversalCommerceConversationEngine()
    decision = engine.decide("buyer", "AC service home visit charge ఎంత? ఎప్పుడు వస్తారు?")
    assert decision.intent == "GENERIC_COMMERCE_QUESTION"


def test_buyer_summary_negotiation_routes_to_change_loop():
    engine = UniversalCommerceConversationEngine()
    deals = FakeDeals(buyer_summary={"request_id": 40, "buyer_user_id": "b", "seller_user_id": "s"})
    decision = engine.decide("b", "price కొంచెం తగ్గించండి", deals=deals)
    assert decision.intent == "BUYER_DOUBT_OR_CHANGE"


def test_command_always_wins_before_semantics():
    engine = UniversalCommerceConversationEngine()
    decision = engine.decide("b", "FINAL_CONFIRM 10 seller")
    assert decision.intent == "COMMAND"
