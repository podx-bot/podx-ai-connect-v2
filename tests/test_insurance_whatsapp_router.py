from app.services.insurance_whatsapp_router import InsuranceWhatsAppRouter


def test_non_insurance_message_is_not_claimed():
    router = InsuranceWhatsAppRouter()
    assert router.process_text("I need a job near Vijayawada") is None


def test_generic_insurance_question_gets_answer():
    router = InsuranceWhatsAppRouter()
    reply = router.process_text("Health insurance waiting period ఎంత?")
    assert reply is not None
    assert "verify" in reply.lower()


def test_policy_specific_question_requests_verified_data():
    router = InsuranceWhatsAppRouter()
    reply = router.process_text("ఈ policyలో coverage ఏమిటి?")
    assert reply is not None
    assert "verified" in reply.lower()


def test_claim_complaint_routes_to_grievance_guidance():
    router = InsuranceWhatsAppRouter()
    reply = router.process_text("My insurance claim was rejected. complaint ఎలా చేయాలి?")
    assert reply is not None
    assert "claim/reference number" in reply
