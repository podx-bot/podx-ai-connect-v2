from app.database.database import Database
from app.repositories.face_welcome_repository import FaceWelcomeRepository
from app.services.face_welcome_enrollment_service import FaceWelcomeEnrollmentService


def build_service(tmp_path):
    database = Database(str(tmp_path / "face-welcome.db"))
    database.create_tables()
    repository = FaceWelcomeRepository(database)
    return database, repository, FaceWelcomeEnrollmentService(repository)


def test_face_welcome_is_optional_and_starts_with_consent(tmp_path):
    database, repository, service = build_service(tmp_path)
    try:
        reply = service.process_text("9191", "face welcome")
        assert "mandatory కాదు" in reply
        assert "consent" in reply
        assert repository.get("9191") is None
    finally:
        database.close()


def test_accept_consent_then_photo_enrollment_stores_digest_not_raw_photo(tmp_path):
    database, repository, service = build_service(tmp_path)
    try:
        reply = service.process_text("9191", "అవును")
        assert "clear front-face photo" in reply
        state = repository.get("9191")
        assert state["consent_status"] == "ACCEPTED"

        image = b"fake-face-image-bytes"
        photo_reply = service.accept_photo("9191", image)
        assert "enrollment save అయింది" in photo_reply

        state = repository.get("9191")
        assert state["photo_sha256"]
        assert state["photo_sha256"] != image.decode()
        assert state["enabled"] == 1
        assert service.status_text("9191") == "Face Welcome: Enabled · Photo enrolled"
    finally:
        database.close()


def test_photo_is_not_accepted_without_explicit_consent(tmp_path):
    database, repository, service = build_service(tmp_path)
    try:
        assert service.accept_photo("9191", b"face") is None
        assert repository.get("9191") is None
    finally:
        database.close()


def test_decline_keeps_normal_profile_without_photo(tmp_path):
    database, repository, service = build_service(tmp_path)
    try:
        reply = service.process_text("9191", "వద్దు")
        assert "normal PODX profile" in reply
        state = repository.get("9191")
        assert state["consent_status"] == "DECLINED"
        assert state["enabled"] == 0
        assert not state["photo_sha256"]
    finally:
        database.close()


def test_disable_revokes_and_clears_photo_reference(tmp_path):
    database, repository, service = build_service(tmp_path)
    try:
        service.process_text("9191", "అవును")
        service.accept_photo("9191", b"face")
        reply = service.process_text("9191", "disable face welcome")
        assert "off చేశాను" in reply
        state = repository.get("9191")
        assert state["consent_status"] == "REVOKED"
        assert state["enabled"] == 0
        assert state["photo_sha256"] is None
    finally:
        database.close()
