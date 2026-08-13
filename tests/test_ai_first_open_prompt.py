from app.services.marketplace_conversation_service import MarketplaceConversationService


def test_home_prompt_is_open_ended():
    prompt = MarketplaceConversationService._main_menu()
    assert "మీకు ఏ విధంగా సహాయం చేయాలి?" in prompt
    assert "voiceగా" in prompt
    assert "Chicken కొనాలి" in prompt
    assert "Electrician service చేస్తాను" in prompt
    assert "1. ఉద్యోగం కావాలి" not in prompt
