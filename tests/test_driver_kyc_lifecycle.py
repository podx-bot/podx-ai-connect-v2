from datetime import date, timedelta

from app.repositories.driver_kyc_repository import DriverKYCRepository
from app.services.driver_kyc_runtime_service import DriverKYCAwareConversationService, DriverKYCRuntimeService


class Delegate:
    def handle_text_message(self, sender, text):
        return f"delegate:{text}"


def _complete(runtime, driver="driver"):
    future = (date.today() + timedelta(days=365)).isoformat()
    runtime.process(driver, "KYC START")
    runtime.process(driver, f"KYC DL AP12345 | {future} | dl-media")
    runtime.process(driver, "KYC VEHICLE AP16AB1234 | Maruti Swift | rc-media")
    runtime.process(driver, f"KYC INSURANCE POL123 | {future} | ins-media")
    runtime.process(driver, "KYC PHOTO car-photo-media")


def test_driver_can_complete_and_submit_kyc(tmp_path):
    repo = DriverKYCRepository(str(tmp_path / "kyc.db"))
    runtime = DriverKYCRuntimeService(repo, admin_mobile="admin")
    _complete(runtime)
    reply = runtime.process("driver", "KYC SUBMIT")
    assert "reviewకి submit" in reply
    state = repo.status("driver")
    assert state["status"] == "SUBMITTED"
    assert state["missing"] == []
    assert not state["eligible"]


def test_submit_reports_missing_documents(tmp_path):
    repo = DriverKYCRepository(str(tmp_path / "kyc_missing.db"))
    runtime = DriverKYCRuntimeService(repo, admin_mobile="admin")
    runtime.process("driver", "KYC START")
    reply = runtime.process("driver", "KYC SUBMIT")
    assert "DL" in reply and "INSURANCE" in reply and "VEHICLE_PHOTO" in reply
    assert repo.status("driver")["status"] == "DRAFT"


def test_only_admin_can_approve_and_approval_makes_driver_eligible(tmp_path):
    repo = DriverKYCRepository(str(tmp_path / "kyc_review.db"))
    runtime = DriverKYCRuntimeService(repo, admin_mobile="admin")
    _complete(runtime)
    runtime.process("driver", "KYC SUBMIT")
    denied = runtime.process("driver", "KYC APPROVE driver")
    assert "admin/internal" in denied
    approved = runtime.process("admin", "KYC APPROVE driver")
    assert "approved" in approved
    state = repo.status("driver")
    assert state["status"] == "APPROVED"
    assert state["eligible"]
    assert all(doc["status"] == "APPROVED" for doc in state["documents"])


def test_rejected_document_resubmission_returns_profile_to_draft(tmp_path):
    repo = DriverKYCRepository(str(tmp_path / "kyc_reject.db"))
    runtime = DriverKYCRuntimeService(repo, admin_mobile="admin")
    _complete(runtime)
    runtime.process("driver", "KYC SUBMIT")
    runtime.process("admin", "KYC REJECT driver | insurance image unclear")
    assert repo.status("driver")["status"] == "REJECTED"
    future = (date.today() + timedelta(days=400)).isoformat()
    runtime.process("driver", f"KYC INSURANCE POL999 | {future} | new-ins-media")
    assert repo.status("driver")["status"] == "DRAFT"


def test_expired_approved_document_disables_verification(tmp_path):
    repo = DriverKYCRepository(str(tmp_path / "kyc_expired.db"))
    runtime = DriverKYCRuntimeService(repo, admin_mobile="admin")
    future = (date.today() + timedelta(days=365)).isoformat()
    past = (date.today() - timedelta(days=1)).isoformat()
    runtime.process("driver", "KYC START")
    runtime.process("driver", f"KYC DL AP12345 | {past} | dl-media")
    runtime.process("driver", "KYC VEHICLE AP16AB1234 | Maruti Swift | rc-media")
    runtime.process("driver", f"KYC INSURANCE POL123 | {future} | ins-media")
    runtime.process("driver", "KYC PHOTO car-photo-media")
    runtime.process("driver", "KYC SUBMIT")
    runtime.process("admin", "KYC APPROVE driver")
    state = repo.status("driver")
    assert "DL" in state["expired"]
    assert not state["eligible"]
    assert "renewal required" in runtime.process("driver", "KYC STATUS")


def test_expiry_queue_includes_upcoming_documents(tmp_path):
    repo = DriverKYCRepository(str(tmp_path / "kyc_expiry.db"))
    runtime = DriverKYCRuntimeService(repo, admin_mobile="admin")
    soon = (date.today() + timedelta(days=10)).isoformat()
    later = (date.today() + timedelta(days=365)).isoformat()
    runtime.process("driver", "KYC START")
    runtime.process("driver", f"KYC DL AP12345 | {soon} | dl-media")
    runtime.process("driver", "KYC VEHICLE AP16AB1234 | Maruti Swift | rc-media")
    runtime.process("driver", f"KYC INSURANCE POL123 | {later} | ins-media")
    runtime.process("driver", "KYC PHOTO car-photo-media")
    runtime.process("driver", "KYC SUBMIT")
    runtime.process("admin", "KYC APPROVE driver")
    expiring = repo.list_expiring(30)
    assert len(expiring) == 1
    assert expiring[0]["doc_type"] == "DL"


def test_kyc_wrapper_delegates_non_kyc_messages(tmp_path):
    repo = DriverKYCRepository(str(tmp_path / "kyc_delegate.db"))
    runtime = DriverKYCRuntimeService(repo, admin_mobile="admin")
    wrapper = DriverKYCAwareConversationService(runtime, Delegate())
    assert wrapper.handle_text_message("driver", "hello") == "delegate:hello"
