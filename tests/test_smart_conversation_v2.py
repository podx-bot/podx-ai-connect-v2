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

    def get(self, sender_mobile):
        return self.session

    def save(self, sender_mobile):
        pass

    def reset(self, sender_mobile):
        self.session = FakeSession()


class FakeUserRepository:
    def __init__(self):
        self.worker_profile = None

    def find_by_whatsapp_mobile(self, sender_mobile):
        return {"registration_complete": 1, "entered_mobile": "9876543210", "area": "Vijayawada"}

    def save_worker_profile(self, **kwargs):
        self.worker_profile = kwargs

    def save_employer_post(self, **kwargs):
        return 1


class ForcedIntentRouter:
    def __init__(self, rule_intent=None, routed_intent="UNKNOWN"):
        self.rule_intent = rule_intent
        self.routed_intent = routed_intent

    def _classify_rules(self, message):
        return self.rule_intent

    def classify(self, message):
        return {"intent": self.routed_intent, "confidence": 1.0}


def build_service(intent_router=None):
    users = FakeUserRepository()
    registry = FakeRegistry()
    service = IntentAwareConversationService(
        user_repository=users,
        session_registry=registry,
        intent_router=intent_router or IntentRouterService(api_key=""),
        appointment_service=None,
    )
    return service, users, registry


def test_telugu_experience_morphology_two_years():
    details = SmartJobMessageService().extract("నాకు రెండు సంవత్సరాల experience ఉంది")
    assert details["experience"] == "1-2 Years"


def test_telugu_compact_two_years_phrase():
    details = SmartJobMessageService().extract("రెండేళ్లు delivery experience ఉంది")
    assert details["experience"] == "1-2 Years"
    assert details["category"] == "Delivery"


def test_numeric_experience_is_bucketed():
    extractor = SmartJobMessageService()
    assert extractor.extract("4 yrs experience")["experience"] == "3-5 Years"
    assert extractor.extract("7 years experience")["experience"] == "5+ Years"


def test_telugu_worker_count_words_are_extracted():
    details = SmartJobMessageService().extract("ఈరోజు ఇద్దరు delivery workers కావాలి")
    assert details["required_workers"] == 2
    assert details["category"] == "Delivery"
    assert details["availability"] == "Today"


def test_followup_natural_telugu_experience_uses_prefilled_tomorrow_and_goes_to_location():
    service, users, registry = build_service()

    first_reply = service.process(
        "9199",
        "నాకు డెలివరీ బాయ్ పని కావాలి, రేపటి నుంచి వస్తాను",
    )
    assert registry.session.step == ConversationStep.WORKER_EXPERIENCE
    assert "Experience" in first_reply

    second_reply = service.process("9199", "నాకు రెండు సంవత్సరాల experience ఉంది")

    assert users.worker_profile == {
        "whatsapp_mobile": "9199",
        "category": "Delivery",
        "experience": "1-2 Years",
        "availability": "Tomorrow",
    }
    assert registry.session.step == ConversationStep.WORKER_LOCATION
    assert "Current Location" in second_reply


def test_single_message_can_capture_category_experience_and_availability():
    service, users, registry = build_service()

    reply = service.process(
        "9199",
        "నాకు delivery boy పని కావాలి, రెండు సంవత్సరాల experience ఉంది, రేపటి నుంచి వస్తాను",
    )

    assert users.worker_profile["category"] == "Delivery"
    assert users.worker_profile["experience"] == "1-2 Years"
    assert users.worker_profile["availability"] == "Tomorrow"
    assert registry.session.step == ConversationStep.WORKER_LOCATION
    assert "Current Location" in reply


def test_unclear_worker_category_followup_is_short_and_does_not_repeat_full_menu():
    service, users, registry = build_service()
    registry.session.step = ConversationStep.WORKER_CATEGORY
    registry.session.data = {"role": "WORKER"}

    reply = service.process("9199", "హలో podx వినిపిస్తుందా")

    assert registry.session.step == ConversationStep.WORKER_CATEGORY
    assert "ఏ పని కావాలో పేరు చెప్పండి" in reply
    assert "1. Delivery" not in reply
    assert "9. Other" not in reply


def test_valid_category_after_short_prompt_still_advances_to_experience():
    service, users, registry = build_service()
    registry.session.step = ConversationStep.WORKER_CATEGORY
    registry.session.data = {"role": "WORKER"}

    reply = service.process("9199", "delivery")

    assert registry.session.step == ConversationStep.WORKER_EXPERIENCE
    assert registry.session.data["category"] == "Delivery"
    assert "Experience" in reply


def test_explicit_menu_command_keeps_global_menu_behavior():
    service, users, registry = build_service()
    registry.session.step = ConversationStep.WORKER_CATEGORY
    registry.session.data = {"role": "WORKER"}

    service.process("9199", "menu")

    assert registry.session.step == ConversationStep.MAIN_MENU


def test_rule_job_seeker_repeat_inside_worker_category_stays_short():
    router = ForcedIntentRouter(rule_intent="JOB_SEEKER", routed_intent="JOB_SEEKER")
    service, users, registry = build_service(intent_router=router)
    registry.session.step = ConversationStep.WORKER_CATEGORY
    registry.session.data = {"role": "WORKER"}

    reply = service.process("9199", "నాకు పని కావాలి")

    assert registry.session.step == ConversationStep.WORKER_CATEGORY
    assert registry.session.data == {"role": "WORKER"}
    assert "ఏ పని కావాలో పేరు చెప్పండి" in reply
    assert "1. Delivery" not in reply


def test_router_job_seeker_repeat_inside_worker_category_stays_short():
    router = ForcedIntentRouter(rule_intent=None, routed_intent="JOB_SEEKER")
    service, users, registry = build_service(intent_router=router)
    registry.session.step = ConversationStep.WORKER_CATEGORY
    registry.session.data = {"role": "WORKER"}

    reply = service.process("9199", "పని గురించి మాట్లాడాలి")

    assert registry.session.step == ConversationStep.WORKER_CATEGORY
    assert registry.session.data == {"role": "WORKER"}
    assert "ఏ పని కావాలో పేరు చెప్పండి" in reply
    assert "1. Delivery" not in reply


def test_valid_category_wins_even_when_router_would_repeat_job_seeker_intent():
    router = ForcedIntentRouter(rule_intent="JOB_SEEKER", routed_intent="JOB_SEEKER")
    service, users, registry = build_service(intent_router=router)
    registry.session.step = ConversationStep.WORKER_CATEGORY
    registry.session.data = {"role": "WORKER"}

    reply = service.process("9199", "Delivery")

    assert registry.session.step == ConversationStep.WORKER_EXPERIENCE
    assert registry.session.data["category"] == "Delivery"
    assert "Experience" in reply
