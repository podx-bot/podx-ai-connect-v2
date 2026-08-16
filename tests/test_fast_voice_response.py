import asyncio
from types import SimpleNamespace

import app.api.routes.fast_webhook as fast_webhook
from app.api.routes.fast_webhook import VOICE_ACK_TEXT, _process_audio_background


class FakeWhatsApp:
    def __init__(self, events, fail_text=False):
        self.events = events
        self.fail_text = fail_text

    def download_media(self, media_id):
        self.events.append("download")
        return {"success": True, "content": b"audio", "mime_type": "audio/ogg"}

    def send_text_message(self, recipient_mobile=None, message=None, *args, **kwargs):
        if recipient_mobile is None and args:
            recipient_mobile = args[0]
        if message is None and len(args) > 1:
            message = args[1]
        self.events.append(("text", message))
        if self.fail_text:
            raise RuntimeError("text transport unavailable")
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


class FakeInbound:
    def __init__(self):
        self.ids = set()

    def exists(self, provider_message_id):
        return provider_message_id in self.ids

    def save(self, provider_message_id, sender_mobile, message_text):
        self.ids.add(provider_message_id)


class FakeBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args, **kwargs):
        self.tasks.append((func, args, kwargs))


class FakeRequest:
    def __init__(self, container):
        self.app = SimpleNamespace(state=SimpleNamespace(container=container))

    async def json(self):
        return {"object": "whatsapp_business_account"}


def build_container(events, fail_text=False):
    return SimpleNamespace(
        whatsapp_service=FakeWhatsApp(events, fail_text=fail_text),
        voice_assistant_service=FakeVoiceAssistant(events),
        audio_codec_service=FakeCodec(events),
        easy_job_command_service=NoopService(),
        job_lifecycle_service=NoopService(),
        conversation_service=FakeConversation(),
        inbound_message_repository=FakeInbound(),
        settings=SimpleNamespace(voice_reply_enabled=True),
    )


def test_voice_ack_text_is_short_and_immediate_friendly():
    assert "voice" in VOICE_ACK_TEXT.lower()
    assert len(VOICE_ACK_TEXT) < 80


def test_final_text_is_sent_before_tts_voice_reply():
    events = []
    container = build_container(events)
    incoming = SimpleNamespace(
        sender_mobile="919999999999",
        provider_message_id="wamid-1",
        media_id="media-1",
        mime_type="audio/ogg",
    )

    _process_audio_background(container, incoming)

    text_index = next(i for i, event in enumerate(events) if isinstance(event, tuple) and event[0] == "text")
    tts_index = events.index("tts")
    assert events[text_index] == ("text", "FINAL TEXT")
    assert text_index < tts_index


def test_text_transport_exception_does_not_block_voice_reply():
    events = []
    container = build_container(events, fail_text=True)
    incoming = SimpleNamespace(
        sender_mobile="919999999999",
        provider_message_id="wamid-2",
        media_id="media-2",
        mime_type="audio/ogg",
    )

    _process_audio_background(container, incoming)

    assert ("text", "FINAL TEXT") in events
    assert "tts" in events
    assert "voice_send" in events


def test_mixed_audio_and_status_batch_keeps_fast_audio_path(monkeypatch):
    events = []
    container = build_container(events)
    incoming = SimpleNamespace(
        sender_mobile="919999999999",
        provider_message_id="wamid-mixed",
        media_id="media-mixed",
        mime_type="audio/ogg",
    )
    background = FakeBackgroundTasks()
    legacy_calls = []

    monkeypatch.setattr(fast_webhook, "extract_audio_messages", lambda payload: [incoming])
    monkeypatch.setattr(fast_webhook, "extract_image_messages", lambda payload: [])
    monkeypatch.setattr(fast_webhook, "extract_document_messages", lambda payload: [])
    monkeypatch.setattr(fast_webhook, "extract_text_messages", lambda payload: [])
    monkeypatch.setattr(fast_webhook, "extract_location_messages", lambda payload: [])
    monkeypatch.setattr(fast_webhook, "extract_delivery_statuses", lambda payload: [object()])

    async def fake_legacy(request):
        legacy_calls.append(True)
        assert container.inbound_message_repository.exists("wamid-mixed")
        return {"status": "processed"}

    monkeypatch.setattr(fast_webhook, "legacy_receive_webhook", fake_legacy)

    result = asyncio.run(fast_webhook.receive_webhook(FakeRequest(container), background))

    assert result["background_audio_count"] == 1
    assert result["legacy_followup_status"] == "processed"
    assert len(background.tasks) == 1
    assert legacy_calls == [True]
    assert ("text", VOICE_ACK_TEXT) in events


def test_ack_send_exception_does_not_cancel_background_audio(monkeypatch):
    events = []
    container = build_container(events, fail_text=True)
    incoming = SimpleNamespace(
        sender_mobile="919999999999",
        provider_message_id="wamid-ack-fail",
        media_id="media-ack-fail",
        mime_type="audio/ogg",
    )
    background = FakeBackgroundTasks()

    monkeypatch.setattr(fast_webhook, "extract_audio_messages", lambda payload: [incoming])
    monkeypatch.setattr(fast_webhook, "extract_image_messages", lambda payload: [])
    monkeypatch.setattr(fast_webhook, "extract_document_messages", lambda payload: [])
    monkeypatch.setattr(fast_webhook, "extract_text_messages", lambda payload: [])
    monkeypatch.setattr(fast_webhook, "extract_location_messages", lambda payload: [])
    monkeypatch.setattr(fast_webhook, "extract_delivery_statuses", lambda payload: [])

    result = asyncio.run(fast_webhook.receive_webhook(FakeRequest(container), background))

    assert result["background_audio_count"] == 1
    assert container.inbound_message_repository.exists("wamid-ack-fail")
    assert len(background.tasks) == 1
