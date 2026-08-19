from app.services.insurance_assistant_service import InsuranceAssistantService


def test_generic_health_waiting_period_guidance_does_not_invent_duration():
    service = InsuranceAssistantService()
    result = service.answer("Health insurance waiting period ఎంత?")

    assert result["status"] == "GENERIC_GUIDANCE"
    assert result["intent"].category == "health"
    assert result["intent"].topic == "waiting_period"
    assert "verify" in result["answer"].lower()


def test_policy_specific_question_requires_verified_product_data():
    service = InsuranceAssistantService()
    result = service.answer("ఈ policyలో coverage ఏమిటి?")

    assert result["status"] == "VERIFIED_PRODUCT_DATA_REQUIRED"
    assert result["next_action"] == "REQUEST_VERIFIED_POLICY_SOURCE"


def test_verified_product_answer_uses_only_supplied_field():
    service = InsuranceAssistantService()
    result = service.answer(
        "ఈ policyలో waiting period ఎంత?",
        verified_product={
            "waiting_period": "Pre-existing disease waiting period: 24 months.",
            "source": "insurer-policy-wording-v1",
        },
    )

    assert result["status"] == "VERIFIED_PRODUCT_ANSWER"
    assert result["answer"] == "Pre-existing disease waiting period: 24 months."
    assert result["source"] == "insurer-policy-wording-v1"


def test_missing_verified_field_refuses_to_guess():
    service = InsuranceAssistantService()
    result = service.answer(
        "ఈ policy premium ఎంత?",
        verified_product={"coverage": "5 lakh", "source": "verified-product-record"},
    )

    assert result["status"] == "VERIFIED_FIELD_MISSING"
    assert result["next_action"] == "VERIFY_MISSING_FIELD"


def test_claim_rejection_goes_to_complaint_escalation_flow():
    service = InsuranceAssistantService()
    result = service.answer("My insurance claim was rejected. complaint ఎలా చేయాలి?")

    assert result["status"] == "ESCALATE_WITH_GUIDANCE"
    assert result["intent"].topic == "grievance"
    assert result["next_action"] == "COLLECT_CASE_DETAILS_AND_ESCALATE"


def test_comparison_explains_multiple_dimensions():
    service = InsuranceAssistantService()
    result = service.answer("Which insurance is better? compare చేయండి")

    assert result["status"] == "GENERIC_GUIDANCE"
    assert result["intent"].topic == "comparison"
    answer = result["answer"].lower()
    assert "premium" in answer
    assert "exclusions" in answer
    assert "claim" in answer
