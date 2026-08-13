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


def test_spoken_reply_does_not_read_long_web_url():
    service = VoiceAssistantService(api_key="test-key")
    prepared = service.prepare_spoken_text(
        "Job location: https://maps.google.com/?q=16.3,80.8 ఇప్పుడు బయలుదేరండి"
    )

    assert "https://" not in prepared
    assert "లింక్ టెక్స్ట్ మెసేజ్‌లో ఉంది" in prepared
    assert "ఇప్పుడు బయలుదేరండి" in prepared


def test_spoken_reply_respects_max_character_limit():
    service = VoiceAssistantService(api_key="test-key", voice_reply_max_chars=100)
    prepared = service.prepare_spoken_text("పని " * 100)

    assert len(prepared) <= 100


def test_long_job_category_menu_becomes_short_natural_voice_prompt():
    service = VoiceAssistantService(api_key="test-key")
    text_reply = (
        "💼 మీరు ఏ పని కోసం చూస్తున్నారు?\n\n"
        "1. Delivery\n2. Catering\n3. Warehouse\n4. Hotel\n"
        "5. House Cleaning\n6. Driver\n7. AC Technician\n"
        "8. Electrician\n9. Other"
    )

    prepared = service.prepare_spoken_text(text_reply)

    assert "1. Delivery" not in prepared
    assert "9. Other" not in prepared
    assert "నేరుగా చెప్పండి" in prepared
    assert "Driver" in prepared
    assert len(prepared) < 180


def test_employer_category_menu_gets_short_worker_prompt():
    service = VoiceAssistantService(api_key="test-key")
    text_reply = (
        "Employer workflow. వర్కర్స్ కావాలి.\n"
        "1. Delivery\n2. Catering\n3. Warehouse\n4. Hotel\n"
        "5. House Cleaning\n6. Driver\n7. AC Technician\n"
        "8. Electrician\n9. Other"
    )

    prepared = service.prepare_spoken_text(text_reply)

    assert "workers కావాలో" in prepared
    assert "1. Delivery" not in prepared


def test_appointment_menu_becomes_short_voice_prompt():
    service = VoiceAssistantService(api_key="test-key")
    prepared = service.prepare_spoken_text(
        "📅 Appointment booking ప్రారంభిద్దాం.\n\n"
        "ఏది కావాలి?\n"
        "1. Doctor\n2. Hospital/Clinic\n3. Salon\n4. Beauty Parlour\n5. Other"
    )

    assert "1. Doctor" not in prepared
    assert "appointment type" in prepared
    assert len(prepared) < 120


def test_appointment_steps_are_short_for_voice():
    service = VoiceAssistantService(api_key="test-key")

    area = service.prepare_spoken_text(
        "✅ Salon. ఇప్పుడు మీ area / locality పేరు చెప్పండి."
    )
    date = service.prepare_spoken_text(
        "ఏ రోజు appointment కావాలి? ఉదాహరణ: Today, Tomorrow లేదా 15-08-2026."
    )
    time = service.prepare_spoken_text(
        "ఏ సమయం కావాలి? ఉదాహరణ: 10 AM, 4:30 PM లేదా Evening."
    )
    saved = service.prepare_spoken_text(
        "✅ Appointment request save అయింది. Request ID: #1 Type: Salon"
    )

    assert area == "మీ area లేదా locality పేరు చెప్పండి."
    assert "Today" in date
    assert "10 AM" in time
    assert "text messageలో" in saved


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


class _FailOnLookupDatabase:
    def fetchone(self, query, params):
        raise AssertionError("ordinary request must not query pending invitations")


class _FailOnLookupRepository:
    def __init__(self):
        self.database = _FailOnLookupDatabase()

    def active_assignment_for_worker(self, worker_mobile):
        raise AssertionError("ordinary request must not query active assignments")


def test_easy_job_fast_gate_skips_all_lifecycle_lookups_for_service_request():
    lifecycle = _FakeLifecycle()
    service = EasyJobCommandService(_FailOnLookupRepository(), lifecycle)

    assert service.process_text("9199", "Electrician కావాలి") is None
    assert lifecycle.calls == []


def test_easy_job_fast_gate_skips_all_lifecycle_lookups_for_product_request():
    lifecycle = _FakeLifecycle()
    service = EasyJobCommandService(_FailOnLookupRepository(), lifecycle)

    assert service.process_text("9199", "Chicken కావాలి") is None
    assert lifecycle.calls == []
