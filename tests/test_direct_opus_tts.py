from app.services.audio_codec_service import AudioCodecService
from app.services.sarvam_tts_voice_assistant_service import SarvamTTSVoiceAssistantService


def test_sarvam_requests_low_bitrate_opus():
    assert SarvamTTSVoiceAssistantService.TTS_OUTPUT_CODEC == "opus"
    assert SarvamTTSVoiceAssistantService.TTS_OUTPUT_BITRATE == "32k"


def test_existing_ogg_opus_skips_ffmpeg_conversion():
    audio = b"OggS" + b"direct-opus-audio"
    result = AudioCodecService().pcm_to_ogg_opus(audio)

    assert result["success"] is True
    assert result["status"] == "ALREADY_OGG_OPUS"
    assert result["content"] == audio
    assert result["conversion_ms"] == 0
    assert result["conversion_bypass"] is True
