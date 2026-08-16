from app.services.easy_job_command_service import EasyJobCommandService
from app.services.job_consent_lifecycle_service import JobConsentLifecycleService


class FakeWhatsApp:
    def __init__(self):
        self.sent = []

    def send_text_message(self, recipient_mobile, message):
        self.sent.append((str(recipient_mobile), str(message)))


class FakeRepo:
    def __init__(self, status="CONFIRMED"):
        self.status = status
        self.database = self

    def accept_job(self, job_id, worker_mobile):
        return {
            "ok": True,
            "reason": "ACCEPTED",
            "job": {
                "id": job_id,
                "employer_mobile": "919900000001",
                "latitude": None,
                "longitude": None,
            },
            "assignment": {"status": "PENDING_CONFIRMATION"},
            "worker": {
                "name": "Ravi",
                "entered_mobile": "9876543210",
                "latitude": None,
                "longitude": None,
            },
        }

    def find_user(self, mobile):
        if str(mobile) == "919800000001":
            return {"name": "Ravi", "entered_mobile": "9876543210"}
        return None

    def find_assignment(self, job_id, worker_mobile):
        return {"employer_job_id": job_id, "worker_mobile": worker_mobile, "status": self.status}

    def find_job(self, job_id):
        return {
            "id": job_id,
            "employer_mobile": "919900000001",
            "employer_contact": "9123456789",
            "service": "Helper",
        }

    def active_assignment_for_worker(self, worker_mobile):
        return {
            "employer_job_id": 7,
            "worker_mobile": worker_mobile,
            "status": self.status,
            "employer_mobile": "919900000001",
            "employer_contact": "9123456789",
        }

    def fetchone(self, sql, params):
        return None


class EmployerConfirmDatabase:
    def fetchone(self, sql, params):
        if "FROM match_notifications" in sql:
            return None
        if "FROM job_assignments" in sql:
            return {"employer_job_id": 44, "worker_mobile": "919800000001"}
        return None


class EasyRepo:
    def __init__(self, database=None):
        self.database = database or self

    def fetchone(self, sql, params):
        return None

    def active_assignment_for_worker(self, worker_mobile):
        return None


class FakeLifecycle:
    def __init__(self):
        self.calls = []

    def process_text(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return "ok"

    def contact_fallback_for_active_job(self, sender_mobile):
        self.calls.append((sender_mobile, "CONTACT_FALLBACK"))
        return "☎️ employer contact: 9123456789"


def test_worker_contact_is_hidden_until_employer_confirms():
    whatsapp = FakeWhatsApp()
    service = JobConsentLifecycleService(FakeRepo(), whatsapp)

    reply = service.process_text("919800000001", "ACCEPT 7")

    assert "Employer confirm" in reply
    assert whatsapp.sent
    employer_message = whatsapp.sent[0][1]
    assert "Contact is hidden" in employer_message
    assert "9876543210" not in employer_message


def test_contact_fallback_is_blocked_before_confirmation():
    whatsapp = FakeWhatsApp()
    service = JobConsentLifecycleService(FakeRepo(status="PENDING_CONFIRMATION"), whatsapp)

    reply = service.process_text("919800000001", "CONTACT 7")

    assert "Employer confirmation" in reply
    assert "9123456789" not in reply
    assert whatsapp.sent == []


def test_confirmed_worker_can_use_phone_contact_fallback():
    whatsapp = FakeWhatsApp()
    service = JobConsentLifecycleService(FakeRepo(status="CONFIRMED"), whatsapp)

    reply = service.process_text("919800000001", "CONTACT 7")

    assert "9123456789" in reply
    assert whatsapp.sent == [
        ("919900000001", "☎️ Job #7 contact fallback\nWorker: Ravi\nContact: 9876543210")
    ]


def test_natural_location_problem_uses_contact_fallback():
    lifecycle = FakeLifecycle()
    easy = EasyJobCommandService(EasyRepo(), lifecycle)

    reply = easy.process_text("919800000001", "లోకేషన్ షేర్ చేయలేను, ఫోన్ నంబర్ ఇవ్వండి")

    assert "9123456789" in reply
    assert lifecycle.calls == [("919800000001", "CONTACT_FALLBACK")]


def test_employer_can_confirm_latest_pending_worker_naturally():
    lifecycle = FakeLifecycle()
    easy = EasyJobCommandService(EasyRepo(EmployerConfirmDatabase()), lifecycle)

    reply = easy.process_text("919900000001", "ఇతనిని తీసుకోండి")

    assert reply == "ok"
    assert lifecycle.calls == [("919900000001", "CONFIRM 44 919800000001")]
