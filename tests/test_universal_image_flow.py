from types import SimpleNamespace

from app.repositories.universal_image_pending_repository import UniversalImagePendingRepository
from app.services.universal_image_service import UniversalImageService
from app.whatsapp.payload_parser import extract_image_messages


class FakeModels:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.text)


class FakeClient:
    def __init__(self, text):
        self.models = FakeModels(text)


class FakeLive:
    def __init__(self):
        self.calls = []

    def process_structured(self, sender_mobile, request, source="text", media_ref=None):
        self.calls.append((sender_mobile, dict(request), source, media_ref))
        return f"saved:{request['side']}:{request['subject']}"


def test_extract_image_message_with_caption():
    payload = {
        "entry": [{"changes": [{"value": {"messages": [{
            "id": "wamid.1",
            "from": "919999999999",
            "type": "image",
            "image": {"id": "media-1", "mime_type": "image/jpeg", "caption": "ఇది కావాలి"},
        }]}}]}]
    }
    messages = extract_image_messages(payload)
    assert len(messages) == 1
    assert messages[0].media_id == "media-1"
    assert messages[0].caption == "ఇది కావాలి"


def test_image_with_clear_caption_goes_directly_to_universal_flow(tmp_path):
    pending = UniversalImagePendingRepository(str(tmp_path / "podx.db"))
    live = FakeLive()
    client = FakeClient('{"side":"NEED","domain":"PRODUCT","subject":"sona masoori rice","quantity":25,"unit":"kg","price":900,"currency":"INR","when_text":null,"location_text":null,"constraints":[],"confidence":0.96}')
    service = UniversalImageService("x", "gemini-test", pending, live, client=client)

    reply = service.process_image("buyer", b"image-bytes", "image/jpeg", "media-1", "ఇది 25kg కావాలి")
    assert reply == "saved:NEED:sona masoori rice"
    assert live.calls[0][2] == "image"
    assert live.calls[0][3] == "media-1"
    assert pending.get("buyer") is None


def test_seller_image_with_offer_caption_creates_offer_record(tmp_path):
    pending = UniversalImagePendingRepository(str(tmp_path / "podx.db"))
    live = FakeLive()
    client = FakeClient('{"side":"OFFER","domain":"PRODUCT","subject":"kirloskar water pump","brand":"Kirloskar","model":"KOS-135","quantity":2,"unit":"pieces","price":6200,"currency":"INR","when_text":null,"location_text":null,"constraints":[],"confidence":0.97}')
    service = UniversalImageService("x", "gemini-test", pending, live, client=client)

    reply = service.process_image("seller", b"seller-image", "image/jpeg", "media-seller", "నా దగ్గర 2 ఉన్నాయి అమ్ముతాను")

    assert reply == "saved:OFFER:kirloskar water pump"
    request = live.calls[0][1]
    assert request["side"] == "OFFER"
    assert "brand:Kirloskar" in request["constraints"]
    assert "model:KOS-135" in request["constraints"]


def test_image_without_intent_asks_once_then_text_completes(tmp_path):
    pending = UniversalImagePendingRepository(str(tmp_path / "podx.db"))
    live = FakeLive()
    client = FakeClient('{"side":"UNKNOWN","domain":"PRODUCT","subject":"water pump","quantity":null,"unit":null,"price":null,"currency":null,"when_text":null,"location_text":null,"constraints":[],"confidence":0.91}')
    service = UniversalImageService("x", "gemini-test", pending, live, client=client)

    first = service.process_image("u1", b"img", "image/jpeg", "media-2", None)
    assert "కావాలా" in first
    assert pending.get("u1") is not None

    second = service.process_text("u1", "నాకు కావాలి")
    assert second == "saved:NEED:water pump"
    assert pending.get("u1") is None
    assert live.calls[-1][1]["side"] == "NEED"


def test_image_then_voice_transcript_can_complete_the_same_pending_intent(tmp_path):
    pending = UniversalImagePendingRepository(str(tmp_path / "podx.db"))
    live = FakeLive()
    client = FakeClient('{"side":"UNKNOWN","domain":"PRODUCT","subject":"pressure cooker","quantity":null,"unit":null,"price":null,"currency":null,"when_text":null,"location_text":null,"constraints":[],"confidence":0.93}')
    service = UniversalImageService("x", "gemini-test", pending, live, client=client)

    first = service.process_image("voice-user", b"img", "image/jpeg", "media-voice", None)
    assert "కావాలా" in first

    # Voice STT enters the same conversation adapter as text, so the transcript must resume this hold.
    second = service.process_text("voice-user", "నేను అమ్మాలి")
    assert second == "saved:OFFER:pressure cooker"
    assert pending.get("voice-user") is None
    assert live.calls[-1][1]["side"] == "OFFER"
