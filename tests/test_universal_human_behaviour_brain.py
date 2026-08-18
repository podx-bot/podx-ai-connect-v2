from app.services.universal_human_behaviour_brain import UniversalHumanBehaviourBrain


def test_category_profiles_cover_jobs_commerce_services_freelance_and_mobility():
    brain = UniversalHumanBehaviourBrain()
    assert "role" in brain.required_fields("job")
    assert "item" in brain.required_fields("product")
    assert "problem_or_scope" in brain.required_fields("service")
    assert "deliverables" in brain.required_fields("freelance")
    assert "pickup" in brain.required_fields("taxi")
    assert "seats" in brain.required_fields("carpool")


def test_negotiation_is_behaviour_not_generic_form_input():
    brain = UniversalHumanBehaviourBrain()
    decision = brain.classify("price కొంచెం తగ్గిస్తారా?")
    assert decision.behaviour == "NEGOTIATE"
    assert brain.next_action(decision.behaviour).action == "ROUTE_TO_COUNTERPARTY"


def test_auto_resolution_escalates_to_direct_contact_after_limit():
    brain = UniversalHumanBehaviourBrain()
    action = brain.next_action("ASK", auto_attempts=2, counterparty_available=True)
    assert action.action == "OFFER_DIRECT_CONTACT"


def test_auto_resolution_escalates_to_human_support_when_no_counterparty():
    brain = UniversalHumanBehaviourBrain()
    action = brain.next_action("COMPLAINT", auto_attempts=2, counterparty_available=False)
    assert action.action == "ESCALATE_HUMAN_SUPPORT"


def test_seller_counter_question_is_detected_inside_pending_revision():
    brain = UniversalHumanBehaviourBrain()
    decision = brain.classify("ఏ color కావాలి?", pending_state="WAITING_SELLER_REVISION")
    assert decision.behaviour == "COUNTER_QUESTION"
