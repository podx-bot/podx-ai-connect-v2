from app.database.database import Database
from app.repositories.job_lifecycle_repository import JobLifecycleRepository
from app.repositories.user_repository import UserRepository
from app.services.job_lifecycle_service import JobLifecycleService


class FakeWhatsAppService:
    def __init__(self):
        self.sent = []

    def send_text_message(self, recipient_mobile: str, message: str):
        self.sent.append((recipient_mobile, message))
        return {
            "success": True,
            "provider_message_id": f"fake-{len(self.sent)}"
        }


def register_user(repo, whatsapp_mobile, entered_mobile, name, category=None):
    repo.create_or_update_registration(
        whatsapp_mobile=whatsapp_mobile,
        entered_mobile=entered_mobile,
        name=name,
        language="Telugu",
        area="Vuyyuru"
    )
    if category:
        repo.save_worker_profile(
            whatsapp_mobile=whatsapp_mobile,
            category=category,
            experience="3-5 Years",
            availability="Today"
        )
        repo.save_location(
            whatsapp_mobile=whatsapp_mobile,
            latitude=16.3695,
            longitude=80.8390
        )
        repo.complete_worker_registration(whatsapp_mobile)


def build(tmp_path):
    database = Database(str(tmp_path / "lifecycle.db"))
    database.create_tables()
    user_repo = UserRepository(database)
    lifecycle_repo = JobLifecycleRepository(database)
    whatsapp = FakeWhatsAppService()
    service = JobLifecycleService(lifecycle_repo, whatsapp)
    return database, user_repo, lifecycle_repo, whatsapp, service


def create_open_job(user_repo, employer_mobile, required=2):
    requirement = f"{required} workers needed today for catering"
    job_id = user_repo.save_employer_post(
        whatsapp_mobile=employer_mobile,
        service="Catering",
        requirement=requirement
    )
    job = user_repo.save_employer_job_location(
        whatsapp_mobile=employer_mobile,
        latitude=16.3696,
        longitude=80.8391,
        location_name="Test Job"
    )
    assert job["id"] == job_id
    assert job["required_workers"] == required
    return job


def test_accept_confirm_contact_exchange_and_status_flow(tmp_path):
    database, user_repo, lifecycle_repo, whatsapp, service = build(tmp_path)
    employer = "919111111111"
    worker = "919222222222"

    register_user(user_repo, employer, "9111111111", "Employer")
    register_user(user_repo, worker, "9222222222", "Worker One", "Catering")
    job = create_open_job(user_repo, employer, required=2)
    job_id = int(job["id"])

    worker_reply = service.process_text(worker, f"ACCEPT {job_id}")
    assert "employer" in worker_reply.lower()
    assert lifecycle_repo.find_assignment(job_id, worker)["status"] == "PENDING_CONFIRMATION"
    assert any(
        recipient == employer
        and "Worker One" in message
        and "9222222222" in message
        and f"CONFIRM {job_id} {worker}" in message
        for recipient, message in whatsapp.sent
    )

    employer_reply = service.process_text(employer, f"CONFIRM {job_id} {worker}")
    assert "1/2" in employer_reply
    assert lifecycle_repo.find_assignment(job_id, worker)["status"] == "CONFIRMED"
    assert any(
        recipient == worker
        and "9111111111" in message
        and "maps.google.com" in message
        and f"ONWAY {job_id}" in message
        for recipient, message in whatsapp.sent
    )

    onway_reply = service.process_text(worker, f"ONWAY {job_id}")
    assert "On the way" in onway_reply
    assert lifecycle_repo.find_assignment(job_id, worker)["status"] == "ON_THE_WAY"

    location_reply = service.handle_location(worker, 16.3696, 80.8391)
    assert "చేరుకున్నట్లు" in location_reply
    assert lifecycle_repo.find_assignment(job_id, worker)["status"] == "ARRIVED"

    start_reply = service.process_text(worker, f"START {job_id}")
    assert "Work started" in start_reply
    complete_reply = service.process_text(worker, f"COMPLETE {job_id}")
    assert "completed" in complete_reply.lower()
    assert lifecycle_repo.find_assignment(job_id, worker)["status"] == "COMPLETED"

    database.close()


def test_required_count_fills_and_closes_job(tmp_path):
    database, user_repo, lifecycle_repo, whatsapp, service = build(tmp_path)
    employer = "919333333333"
    worker1 = "919444444444"
    worker2 = "919555555555"

    register_user(user_repo, employer, "9333333333", "Employer Two")
    register_user(user_repo, worker1, "9444444444", "Worker A", "Catering")
    register_user(user_repo, worker2, "9555555555", "Worker B", "Catering")
    job = create_open_job(user_repo, employer, required=2)
    job_id = int(job["id"])

    service.process_text(worker1, f"ACCEPT {job_id}")
    first = service.process_text(employer, f"CONFIRM {job_id} {worker1}")
    assert "1/2" in first
    assert lifecycle_repo.find_job(job_id)["status"] == "OPEN"

    service.process_text(worker2, f"ACCEPT {job_id}")
    second = service.process_text(employer, f"CONFIRM {job_id} {worker2}")
    assert "2/2" in second
    assert "auto-closed" in second
    assert lifecycle_repo.find_job(job_id)["status"] == "FILLED"

    status_reply = service.process_text(employer, f"STATUS {job_id}")
    assert "2/2" in status_reply
    assert "FILLED" in status_reply

    database.close()


def test_worker_cannot_accept_own_job(tmp_path):
    database, user_repo, lifecycle_repo, whatsapp, service = build(tmp_path)
    employer = "919666666666"
    register_user(user_repo, employer, "9666666666", "Same User", "Catering")
    job = create_open_job(user_repo, employer, required=1)

    reply = service.process_text(employer, f"ACCEPT {job['id']}")
    assert "సొంత" in reply
    assert lifecycle_repo.find_assignment(int(job["id"]), employer) is None

    database.close()
