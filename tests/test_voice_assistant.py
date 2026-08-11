from app.services.easy_job_command_service import EasyJobCommandService
from app.services.voice_assistant_service import VoiceAssistantService
from app.whatsapp.payload_parser import extract_audio_messages


def test_extract_audio_message_from_whatsapp_payload():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "919999999999",
                                    "id": "wamid.voice1",
                                    "type": "audio",
                                    "audio": {
                                        "id": "media-123",
                                        "mime_type": "audio/ogg; codecs=opus",
                                        "voice": True,
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    messages = extract_audio_messages(payload)
    assert len(messages) == 1
    assert messages[0].sender_mobile == "919999999999"
    assert messages[0].media_id == "media-123"
    assert messages[0].is_voice is True


def test_spoken_number_words_normalize_to_menu_digits():
    assert VoiceAssistantService.normalize_spoken_choice("ఒకటి") == "1"
    assert VoiceAssistantService.normalize_spoken_choice("రెండు") == "2"
    assert VoiceAssistantService.normalize_spoken_choice("Three") == "3"
    assert VoiceAssistantService.normalize_spoken_choice("కేటరింగ్") == "కేటరింగ్"


class _FakeDatabase:
    def __init__(self, pending_job_id=None):
        self.pending_job_id = pending_job_id

    def fetchone(self, query, params):
        if self.pending_job_id is None:
            return None
        return {"employer_job_id": self.pending_job_id}


class _FakeRepository:
    def __init__(self, pending_job_id=None, active=None):
        self.database = _FakeDatabase(pending_job_id)
        self.active = active

    def active_assignment_for_worker(self, worker_mobile):
        return self.active


class _FakeLifecycle:
    def __init__(self):
        self.calls = []

    def process_text(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return f"handled:{message}"


def test_easy_one_accepts_only_when_pending_job_exists():
    lifecycle = _FakeLifecycle()
    service = EasyJobCommandService(_FakeRepository(pending_job_id=7), lifecycle)

    assert service.process_text("9199", "1") == "handled:ACCEPT 7"
    assert lifecycle.calls == [("9199", "ACCEPT 7")]


def test_easy_one_does_not_hijack_normal_menu_without_pending_job():
    lifecycle = _FakeLifecycle()
    service = EasyJobCommandService(_FakeRepository(pending_job_id=None), lifecycle)

    assert service.process_text("9199", "1") is None
    assert lifecycle.calls == []


def test_telugu_onway_phrase_uses_active_job_context():
    lifecycle = _FakeLifecycle()
    active = {"employer_job_id": 12, "status": "CONFIRMED"}
    service = EasyJobCommandService(_FakeRepository(active=active), lifecycle)

    assert service.process_text("9199", "నేను బయలుదేరాను") == "handled:ONWAY 12"
