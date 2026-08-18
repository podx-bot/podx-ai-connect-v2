from app.services.dynamic_role_profile_attachment_service import DynamicRoleProfileAttachmentService
from app.services.progressive_role_profile_essentials_service import ProgressiveRoleProfileEssentialsService
from app.services.universal_category_flow_brain import UniversalCategoryFlowBrain


class Users:
    def __init__(self, user):
        self.user = dict(user)
        self.capabilities = set(self.user.get("capabilities") or [])

    def find_by_whatsapp_mobile(self, sender):
        data = dict(self.user)
        data["capabilities"] = list(self.capabilities)
        return data

    def has_capability(self, sender, capability):
        return capability in self.capabilities

    def add_capability(self, sender, capability, source=None):
        self.capabilities.add(capability)


class Session:
    def __init__(self):
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
    def process(self, sender_mobile, message):
        return "DOWNSTREAM"


def test_worker_plan_contains_only_missing_durable_fields():
    users = Users({
        "registration_complete": 1,
        "job_category": "Driver",
        "experience": None,
        "availability": "Today",
        "latitude": 16.5,
        "longitude": 80.6,
    })
    plan = ProgressiveRoleProfileEssentialsService(users).plan_for_user("u", "WORKER")
    assert plan.missing_fields == ("experience",)
    assert plan.complete is False


def test_complete_worker_profile_does_not_request_fields_again():
    users = Users({
        "registration_complete": 1,
        "job_category": "Driver",
        "experience": "5+ Years",
        "availability": "Today",
        "latitude": 16.5,
        "longitude": 80.6,
    })
    plan = ProgressiveRoleProfileEssentialsService(users).plan_for_user("u", "WORKER")
    assert plan.missing_fields == ()
    assert plan.complete is True


def test_location_counts_missing_if_only_one_coordinate_exists():
    users = Users({
        "registration_complete": 1,
        "job_category": "Driver",
        "experience": "5+ Years",
        "availability": "Today",
        "latitude": 16.5,
        "longitude": None,
    })
    plan = ProgressiveRoleProfileEssentialsService(users).plan_for_user("u", "WORKER")
    assert plan.missing_fields == ("location",)


def test_transaction_scoped_roles_do_not_force_permanent_profile_questions():
    users = Users({"registration_complete": 1})
    planner = ProgressiveRoleProfileEssentialsService(users)
    for role in ("BUYER", "SELLER", "SERVICE_CUSTOMER", "SERVICE_PROVIDER", "EMPLOYER"):
        plan = planner.plan_for_user("u", role)
        assert plan.complete is True
        assert plan.missing_fields == ()


def test_intent_attachment_records_missing_only_plan_and_resumes_first_missing_field():
    users = Users({
        "registration_complete": 1,
        "job_category": "Warehouse",
        "experience": None,
        "availability": None,
        "latitude": None,
        "longitude": None,
    })
    sessions = Sessions()
    planner = ProgressiveRoleProfileEssentialsService(users)
    service = DynamicRoleProfileAttachmentService(
        delegate=Delegate(),
        category_brain=UniversalCategoryFlowBrain(),
        user_repository=users,
        profile_essentials=planner,
        session_registry=sessions,
    )

    reply = service.process("u", "job కావాలి")
    assert reply.startswith("మీ Experience ఎంత?")
    assert "WORKER" in users.capabilities
    assert sessions.session.data["active_capability"] == "WORKER"
    assert sessions.session.data["role_profile_missing_fields"] == ["experience", "availability", "location"]
    assert sessions.session.data["role_profile_complete"] is False
    assert sessions.session.data["category"] == "Warehouse"
    assert sessions.saved == ["u", "u"]


def test_profile_planning_never_blocks_downstream_when_session_shape_is_legacy():
    users = Users({"registration_complete": 1})

    class LegacySession:
        pass

    class LegacySessions:
        def get(self, sender):
            return LegacySession()

    service = DynamicRoleProfileAttachmentService(
        delegate=Delegate(),
        category_brain=UniversalCategoryFlowBrain(),
        user_repository=users,
        profile_essentials=ProgressiveRoleProfileEssentialsService(users),
        session_registry=LegacySessions(),
    )
    assert service.process("u", "55 inch TV కావాలి") == "DOWNSTREAM"
    assert "BUYER" in users.capabilities
