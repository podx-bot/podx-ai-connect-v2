from types import SimpleNamespace

from app.api.routes.fast_webhook import VOICE_ACK_TEXT, _process_audio_background


class FakeWhatsApp:
    def __init__(self, events):
        self.events = events

    def download_media(self, media_id):
        self.events.append("download")
        return {"success": True, "content": b"audio", "mime_type": "audio/ogg"}

    def send_text_message(self, recipient_mobile, message):
        self.events.append(("text", message))
        return {"success": True}

    def send_voice_bytes(self, recipient_mobile, audio_bytes, mime_type, file_name):
        self.events.append("voice_send")
        return {"success": True}


class FakeVoiceAssistant:
    def __init__(self, events):
        self.events = events

    def transcribe(self, audio_bytes, mime_type):
        self.events.append("transcribe")
        return {"success": True, "transcript": "నాకు ఉద్యోగం కావాలి"}

    def normalize_spoken_choice(self, transcript):
        return transcript

    def synthesize(self, reply_text):
        self.events.append("tts")
        return {"success": True, "content": b"pcm", "sample_rate": 24000, "channels": 1}


class FakeCodec:
    def __init__(self, events):
        self.events = events

    def pcm_to_ogg_opus(self, pcm_bytes, sample_rate, channels):
        self.events.append("codec")
        return {"success": True, "content": b"ogg", "mime_type": "audio/ogg", "file_name": "reply.ogg"}


class NoopService:
    def process_text(self, **kwargs):
        return None


class FakeConversation:
    def process(self, sender_mobile, message):
        return "FINAL TEXT"


def test_voice_ack_text_is_short_and_immediate_friendly():
    assert "voice" in VOICE_ACK_TEXT.lower()
    assert len(VOICE_ACK_TEXT) < 80


def test_final_text_is_sent_before_tts_voice_reply():
    events = []
    container = SimpleNamespace(
        whatsapp_service=FakeWhatsApp(events),
        voice_assistant_service=FakeVoiceAssistant(events),
        audio_codec_service=FakeCodec(events),
        easy_job_command_service=NoopService(),
        job_lifecycle_service=NoopService(),
        conversation_service=FakeConversation(),
        settings=SimpleNamespace(voice_reply_enabled=True),
    )
    incoming = SimpleNamespace(sender_mobile="919999999999", media_id="media-1", mime_type="audio/ogg")

    _process_audio_background(container, incoming)

    text_index = next(i for i, event in enumerate(events) if isinstance(event, tuple) and event[0] == "text")
    tts_index = events.index("tts")
    assert events[text_index] == ("text", "FINAL TEXT")
    assert text_index < tts_index
