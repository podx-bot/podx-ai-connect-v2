from app.services.voice_assistant_service import VoiceAssistantService


def test_service_request_keeps_text_detail_but_uses_short_spoken_confirmation():
    service = VoiceAssistantService(api_key="test-key")
    text = (
        "🛠️ మీ local service request save చేశాను. ప్రస్తుతం direct match దొరకకపోతే "
        "PODX ఈ demandని track చేసి provider available అయినప్పుడు connect చేయగలదు."
    )

    spoken = service.prepare_spoken_text(text)

    assert spoken == "మీ service request save అయింది. Provider available అయినప్పుడు PODX connect చేస్తుంది."
    assert len(spoken) < len(text)


def test_product_request_uses_short_spoken_confirmation():
    service = VoiceAssistantService(api_key="test-key")
    text = (
        "🛍️ మీ product request save చేశాను. ప్రస్తుతం local match దొరకకపోతే PODX ఈ demandని "
        "track చేసి seller/stock available అయినప్పుడు connect చేయగలదు."
    )

    spoken = service.prepare_spoken_text(text)

    assert spoken == "మీ product request save అయింది. Seller లేదా stock available అయినప్పుడు PODX connect చేస్తుంది."
    assert len(spoken) < len(text)


def test_unrelated_reply_is_not_rewritten_by_short_confirmation_rules():
    service = VoiceAssistantService(api_key="test-key")
    text = "మీ availability ఎప్పుడు? Today, Tomorrow లేదా This Week."

    assert service.prepare_spoken_text(text) == text
