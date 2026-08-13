from app.services.sarvam_tts_voice_assistant_service import SarvamTTSVoiceAssistantService


def test_sarvam_tts_language_detection_for_indian_scripts():
    assert SarvamTTSVoiceAssistantService.detect_tts_language("నాకు సహాయం కావాలి") == "te-IN"
    assert SarvamTTSVoiceAssistantService.detect_tts_language("मुझे मदद चाहिए") == "hi-IN"
    assert SarvamTTSVoiceAssistantService.detect_tts_language("எனக்கு உதவி வேண்டும்") == "ta-IN"
    assert SarvamTTSVoiceAssistantService.detect_tts_language("I need help") == "en-IN"


def test_sarvam_tts_streaming_contract():
    assert SarvamTTSVoiceAssistantService.TTS_URL.endswith("/text-to-speech/stream")
    assert SarvamTTSVoiceAssistantService.TTS_SAMPLE_RATE == 24000
    assert SarvamTTSVoiceAssistantService.TTS_READ_TIMEOUT_SECONDS <= 6.0
