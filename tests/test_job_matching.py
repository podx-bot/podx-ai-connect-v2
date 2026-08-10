from app.database.database import Database
from app.repositories.user_repository import UserRepository
from app.services.job_matching_service import JobMatchingService


class FakeWhatsAppService:
    def __init__(self) -> None:
        self.sent = []

    def send_text_message(self, recipient_mobile: str, message: str):
        self.sent.append((recipient_mobile, message))
        return {
            "success": True,
            "provider_message_id": f"msg-{len(self.sent)}"
        }


def build_repository(tmp_path):
    database = Database(str(tmp_path / "matching.db"))
    database.create_tables()
    return UserRepository(database), database


def create_worker(
    repository: UserRepository,
    mobile: str,
    category: str,
    latitude: float,
    longitude: float
):
    repository.create_or_update_registration(
        whatsapp_mobile=mobile,
        entered_mobile=mobile[-10:],
        name="Worker",
        language="Telugu",
        area="Vuyyuru"
    )
    repository.save_worker_profile(
        whatsapp_mobile=mobile,
        category=category,
        experience="5+ Years",
        availability="Today"
    )
    repository.save_location(
        whatsapp_mobile=mobile,
        latitude=latitude,
        longitude=longitude
    )
    repository.complete_worker_registration(mobile)


def test_employer_post_does_not_overwrite_worker_profile(tmp_path):
    repository, database = build_repository(tmp_path)
    mobile = "919999999999"
    create_worker(repository, mobile, "Catering", 16.3722, 80.8475)

    repository.save_employer_post(
        whatsapp_mobile=mobile,
        service="Delivery",
        requirement="Need 5 delivery workers today"
    )

    worker = repository.find_by_whatsapp_mobile(mobile)
    assert worker["job_category"] == "Catering"
    assert worker["experience"] == "5+ Years"
    assert worker["availability"] == "Today"
    assert worker["worker_registration_complete"] == 1

    database.close()


def test_nearby_worker_is_notified_once(tmp_path):
    repository, database = build_repository(tmp_path)
    worker_mobile = "918888888888"
    employer_mobile = "917777777777"

    create_worker(
        repository,
        worker_mobile,
        "Catering",
        16.3722,
        80.8475
    )
    repository.save_employer_post(
        whatsapp_mobile=employer_mobile,
        service="Catering",
        requirement="10 workers needed today for catering"
    )
    job = repository.save_employer_job_location(
        whatsapp_mobile=employer_mobile,
        latitude=16.3695,
        longitude=80.8390
    )

    whatsapp = FakeWhatsAppService()
    service = JobMatchingService(repository, whatsapp, max_distance_km=25)

    first = service.match_and_notify(job)
    second = service.match_and_notify(job)

    assert first["matched_count"] == 1
    assert first["notified_count"] == 1
    assert second["matched_count"] == 1
    assert second["notified_count"] == 0
    assert len(whatsapp.sent) == 1
    assert whatsapp.sent[0][0] == worker_mobile
    assert "Catering" in whatsapp.sent[0][1]

    database.close()


def test_far_worker_is_not_matched(tmp_path):
    repository, database = build_repository(tmp_path)
    worker_mobile = "916666666666"
    employer_mobile = "915555555555"

    create_worker(
        repository,
        worker_mobile,
        "Catering",
        17.3850,
        78.4867
    )
    repository.save_employer_post(
        whatsapp_mobile=employer_mobile,
        service="Catering",
        requirement="Workers needed"
    )
    job = repository.save_employer_job_location(
        whatsapp_mobile=employer_mobile,
        latitude=16.3695,
        longitude=80.8390
    )

    whatsapp = FakeWhatsAppService()
    service = JobMatchingService(repository, whatsapp, max_distance_km=25)
    result = service.match_and_notify(job)

    assert result["matched_count"] == 0
    assert result["notified_count"] == 0
    assert whatsapp.sent == []

    database.close()


def test_employer_is_not_notified_about_own_job(tmp_path):
    repository, database = build_repository(tmp_path)
    mobile = "914444444444"
    create_worker(repository, mobile, "Catering", 16.3722, 80.8475)
    repository.save_employer_post(
        whatsapp_mobile=mobile,
        service="Catering",
        requirement="Need catering workers"
    )
    job = repository.save_employer_job_location(
        whatsapp_mobile=mobile,
        latitude=16.3695,
        longitude=80.8390
    )

    whatsapp = FakeWhatsAppService()
    service = JobMatchingService(repository, whatsapp, max_distance_km=25)
    result = service.match_and_notify(job)

    assert result["candidate_count"] == 1
    assert result["matched_count"] == 0
    assert result["skipped_self_count"] == 1
    assert whatsapp.sent == []

    database.close()
