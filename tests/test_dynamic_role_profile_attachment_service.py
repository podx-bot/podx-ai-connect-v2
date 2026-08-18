from app.services.dynamic_role_profile_attachment_service import DynamicRoleProfileAttachmentService
from app.services.universal_category_flow_brain import UniversalCategoryFlowBrain


class Users:
    def __init__(self, registered=True):
        self.registered = registered
        self.capabilities = {}
        self.added = []

    def find_by_whatsapp_mobile(self, sender):
        if not self.registered:
            return None
        return {"whatsapp_mobile": sender, "registration_complete": 1}

    def has_capability(self, sender, capability):
        return capability in self.capabilities.get(sender, set())

    def add_capability(self, sender, capability, source=None):
        self.capabilities.setdefault(sender, set()).add(capability)
        self.added.append((sender, capability, source))


class Delegate:
    def __init__(self, reply="DOWNSTREAM"):
        self.reply = reply
        self.calls = []

    def process(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return self.reply


def build(registered=True):
    users = Users(registered=registered)
    delegate = Delegate()
    service = DynamicRoleProfileAttachmentService(
        delegate=delegate,
        category_brain=UniversalCategoryFlowBrain(),
        user_repository=users,
    )
    return service, users, delegate


def test_commerce_buyer_and_seller_are_attached_from_intent():
    service, users, delegate = build()

    assert service.process("u", "55 inch TV కావాలి") == "DOWNSTREAM"
    assert users.has_capability("u", "BUYER")

    assert service.process("u", "TV అమ్మాలి") == "DOWNSTREAM"
    assert users.has_capability("u", "SELLER")
    assert delegate.calls == [("u", "55 inch TV కావాలి"), ("u", "TV అమ్మాలి")]


def test_service_and_jobs_roles_are_attached_without_upfront_menu():
    service, users, _ = build()

    service.process("u", "AC repair కావాలి")
    service.process("u", "నేను electrician service ఇస్తాను")
    service.process("u", "job కావాలి")
    service.process("u", "need 3 workers for warehouse")

    assert users.capabilities["u"] == {
        "SERVICE_CUSTOMER",
        "SERVICE_PROVIDER",
        "WORKER",
        "EMPLOYER",
    }


def test_existing_capability_is_not_added_twice():
    service, users, _ = build()
    users.capabilities["u"] = {"BUYER"}

    service.process("u", "TV కావాలి")

    assert users.added == []


def test_ambiguous_general_text_does_not_force_a_role():
    service, users, delegate = build()

    assert service.process("u", "hello there") == "DOWNSTREAM"
    assert users.added == []
    assert delegate.calls == [("u", "hello there")]


def test_unregistered_user_is_not_enriched_and_downstream_still_runs():
    service, users, delegate = build(registered=False)

    assert service.process("new", "job కావాలి") == "DOWNSTREAM"
    assert users.added == []
    assert delegate.calls == [("new", "job కావాలి")]


def test_capability_enrichment_failure_never_drops_user_message():
    service, users, delegate = build()

    def broken_add(*args, **kwargs):
        raise RuntimeError("db unavailable")

    users.add_capability = broken_add
    assert service.process("u", "job కావాలి") == "DOWNSTREAM"
    assert delegate.calls == [("u", "job కావాలి")]
