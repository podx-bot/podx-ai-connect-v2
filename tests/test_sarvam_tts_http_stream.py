from app.services.sarvam_tts_voice_assistant_service import SarvamTTSVoiceAssistantService


def test_tts_stream_endpoint_and_sample_rate():
    assert SarvamTTSVoiceAssistantService.TTS_URL.endswith("/text-to-speech/stream")
    assert SarvamTTSVoiceAssistantService.TTS_SAMPLE_RATE == 24000


def test_tts_language_detection():
    assert SarvamTTSVoiceAssistantService.detect_tts_language("మీకు సహాయం చేస్తాను") == "te-IN"
    assert SarvamTTSVoiceAssistantService.detect_tts_language("I can help you") == "en-IN"
