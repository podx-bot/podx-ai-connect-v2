import io
import wave

from app.services.sarvam_tts_voice_assistant_service import SarvamTTSVoiceAssistantService


def test_sarvam_tts_language_detection_for_indian_scripts():
    assert SarvamTTSVoiceAssistantService.detect_tts_language("నాకు సహాయం కావాలి") == "te-IN"
    assert SarvamTTSVoiceAssistantService.detect_tts_language("मुझे मदद चाहिए") == "hi-IN"
    assert SarvamTTSVoiceAssistantService.detect_tts_language("எனக்கு உதவி வேண்டும்") == "ta-IN"
    assert SarvamTTSVoiceAssistantService.detect_tts_language("I need help") == "en-IN"


def test_sarvam_wav_to_pcm_extracts_audio_frames():
    pcm = (b"\x01\x00" * 160)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(pcm)

    decoded, sample_rate, channels = SarvamTTSVoiceAssistantService.wav_to_pcm(buffer.getvalue())
    assert decoded == pcm
    assert sample_rate == 24000
    assert channels == 1
