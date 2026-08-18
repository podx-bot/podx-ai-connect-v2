from dataclasses import dataclass

from app.models.session import ConversationStep
from app.services.dynamic_role_profile_attachment_service import DynamicRoleProfileAttachmentService
from app.services.universal_category_flow_brain import UniversalCategoryFlowBrain


@dataclass
class Plan:
    missing_fields: tuple[str, ...]
    complete: bool = False


class Users:
    def __init__(self, user):
        self.user = user
        self.capabilities = set()

    def find_by_whatsapp_mobile(self, sender):
        return dict(self.user)

    def has_capability(self, sender, capability):
        return capability in self.capabilities

    def add_capability(self, sender, capability, source=None):
        self.capabilities.add(capability)


class Planner:
    def __init__(self, missing):
        self.missing = tuple(missing)

    def plan_for_user(self, sender, capability):
        return Plan(self.missing, not self.missing)


class Session:
    def __init__(self):
        self.step = ConversationStep.MAIN_MENU
        self.data = {}


class Sessions:
    def __init__(self):
        self.session = Session()
        self.saved = []

    def get(self, sender):
        return self.session

    def save(self, sender):
        self.saved.append(sender)


class Delegate:
    def __init__(self):
        self.calls = []

    def process(self, sender, message):
        self.calls.append((sender, message))
        return "DOWNSTREAM"


def build(missing, **saved_fields):
    user = {"registration_complete": 1, **saved_fields}
    users = Users(user)
    sessions = Sessions()
    delegate = Delegate()
    service = DynamicRoleProfileAttachmentService(
        delegate=delegate,
        category_brain=UniversalCategoryFlowBrain(),
        user_repository=users,
        profile_essentials=Planner(missing),
        session_registry=sessions,
    )
    return service, sessions, delegate


def test_worker_with_no_durable_details_starts_at_category_only():
    service, sessions, delegate = build(("job_category", "experience", "availability", "location"))

    reply = service.process("u", "job కావాలి")

    assert "ఏ పని" in reply
    assert sessions.session.step == ConversationStep.WORKER_CATEGORY
    assert delegate.calls == []


def test_saved_category_is_reused_and_experience_is_next():
    service, sessions, delegate = build(
        ("experience", "availability", "location"),
        job_category="Driver",
    )

    reply = service.process("u", "job కావాలి")

    assert "Experience" in reply
    assert sessions.session.step == ConversationStep.WORKER_EXPERIENCE
    assert sessions.session.data["category"] == "Driver"
    assert delegate.calls == []


def test_saved_category_experience_are_reused_and_availability_is_next():
    service, sessions, delegate = build(
        ("availability", "location"),
        job_category="Electrician",
        experience="3-5 Years",
    )

    reply = service.process("u", "పని కావాలి")

    assert "Availability" in reply
    assert sessions.session.step == ConversationStep.WORKER_AVAILABILITY
    assert sessions.session.data["category"] == "Electrician"
    assert sessions.session.data["experience"] == "3-5 Years"
    assert delegate.calls == []


def test_only_missing_location_skips_every_previous_worker_question():
    service, sessions, delegate = build(
        ("location",),
        job_category="Warehouse",
        experience="1-2 Years",
        availability="Today",
    )

    reply = service.process("u", "job కావాలి")

    assert "Location మాత్రమే" in reply
    assert sessions.session.step == ConversationStep.WORKER_LOCATION
    assert sessions.session.data["category"] == "Warehouse"
    assert sessions.session.data["experience"] == "1-2 Years"
    assert sessions.session.data["availability"] == "Today"
    assert delegate.calls == []


def test_complete_worker_profile_does_not_invent_a_new_profile_question():
    service, sessions, delegate = build(
        (),
        job_category="Driver",
        experience="5+ Years",
        availability="Today",
        latitude=16.5,
        longitude=80.6,
    )

    assert service.process("u", "job కావాలి") == "DOWNSTREAM"
    assert delegate.calls == [("u", "job కావాలి")]


def test_non_worker_roles_remain_transaction_scoped_and_go_downstream():
    service, sessions, delegate = build(())

    assert service.process("u", "AC repair కావాలి") == "DOWNSTREAM"
    assert delegate.calls == [("u", "AC repair కావాలి")]
