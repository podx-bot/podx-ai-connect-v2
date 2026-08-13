from app.models.session import ConversationStep
from app.services.intent_aware_conversation_service import IntentAwareConversationService
from app.services.intent_router_service import IntentRouterService
from app.services.smart_job_message_service import SmartJobMessageService


class FakeSession:
    def __init__(self):
        self.step = ConversationStep.MAIN_MENU
        self.data = {}


class FakeRegistry:
    def __init__(self):
        self.session = FakeSession()
        self.saved = []

    def get(self, sender_mobile):
        return self.session

    def save(self, sender_mobile):
        self.saved.append(sender_mobile)

    def reset(self, sender_mobile):
        self.session = FakeSession()


class FakeUserRepository:
    def __init__(self):
        self.worker_profile = None
        self.employer_post = None

    def find_by_whatsapp_mobile(self, sender_mobile):
        return {
            "registration_complete": 1,
            "entered_mobile": "9876543210",
            "area": "Vijayawada",
        }

    def save_worker_profile(self, **kwargs):
        self.worker_profile = kwargs

    def save_employer_post(self, **kwargs):
        self.employer_post = kwargs
        return 1


def build_service():
    users = FakeUserRepository()
    registry = FakeRegistry()
    service = IntentAwareConversationService(
        user_repository=users,
        session_registry=registry,
        intent_router=IntentRouterService(api_key=""),
        appointment_service=None,
    )
    return service, users, registry


def test_extractor_finds_category_availability_and_worker_count():
    details = SmartJobMessageService().extract(
        "రేపు 3 workers delivery కోసం కావాలి"
    )
    assert details["category"] == "Delivery"
    assert details["availability"] == "Tomorrow"
    assert details["required_workers"] == 3


def test_worker_message_skips_known_category_and_availability():
    service, users, registry = build_service()

    reply = service.process(
        "9199",
        "నాకు డెలివరీ బాయ్ పని కావాలి, రేపటి నుంచి వస్తాను",
    )

    assert registry.session.step == ConversationStep.WORKER_EXPERIENCE
    assert registry.session.data["category"] == "Delivery"
    assert registry.session.data["availability"] == "Tomorrow"
    assert "Experience" in reply

    reply = service.process("9199", "ఫ్రెషర్")

    assert users.worker_profile["category"] == "Delivery"
    assert users.worker_profile["experience"] == "Fresher"
    assert users.worker_profile["availability"] == "Tomorrow"
    assert registry.session.step == ConversationStep.WORKER_LOCATION
    assert "Current Location" in reply


def test_employer_delivery_boy_request_goes_directly_to_location():
    service, users, registry = build_service()
    message = "నాకు అర్జెంట్గా సరుకులు delivery చేయడానికి delivery boy కావాలి"

    reply = service.process("9199", message)

    assert users.employer_post["service"] == "Delivery"
    assert users.employer_post["requirement"] == message
    assert registry.session.step == ConversationStep.EMPLOYER_LOCATION
    assert "Job Location" in reply


def test_job_seeker_wording_wins_over_delivery_boy_hiring_phrase():
    router = IntentRouterService(api_key="")
    result = router.classify("నాకు delivery boy పని కావాలి")
    assert result["intent"] == "JOB_SEEKER"
