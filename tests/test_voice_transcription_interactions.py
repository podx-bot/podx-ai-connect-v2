from unittest.mock import MagicMock, patch

from app.services.voice_assistant_service import VoiceAssistantService


def test_transcribe_uses_interactions_audio_input():
    service = VoiceAssistantService(api_key="test-key", model="gemini-3.6-flash")
    interaction = MagicMock()
    interaction.output_text = "హాయ్"
    client = MagicMock()
    client.interactions.create.return_value = interaction

    with patch("app.services.voice_assistant_service.genai.Client", return_value=client):
        result = service.transcribe(b"ogg-bytes", "audio/ogg; codecs=opus")

    assert result["success"] is True
    assert result["transcript"] == "హాయ్"
    assert result["mime_type"] == "audio/ogg"
    kwargs = client.interactions.create.call_args.kwargs
    assert kwargs["model"] == "gemini-3.6-flash"
    assert kwargs["input"][1]["type"] == "audio"
    assert kwargs["input"][1]["mime_type"] == "audio/ogg"
