from app.services.insurance_assistant_service import InsuranceAssistantService


def test_health_category_is_not_asked_again():
    service = InsuranceAssistantService()
    result = service.answer("మా ఫ్యామిలీకి హెల్త్ ఇన్సూరెన్స్ తీసుకోవాలి")

    assert result["intent"].category == "health"
    answer = result["answer"].lower()
    assert "ఏ insurance" not in answer
    assert "health" in answer
    assert "వయస" in answer or "ages" in answer


def test_general_insurance_still_asks_for_category():
    service = InsuranceAssistantService()
    result = service.answer("నాకు insurance కావాలి")

    assert result["intent"].category == "general"
    assert "ఏ insurance" in result["answer"]
