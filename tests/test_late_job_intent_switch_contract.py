from app.models.session import ConversationStep
from app.services.intent_aware_conversation_service import IntentAwareConversationService


def test_all_late_job_steps_allow_clear_intent_switching():
    steps = IntentAwareConversationService.INTENT_SWITCH_STEPS
    assert ConversationStep.WORKER_LOCATION in steps
    assert ConversationStep.EMPLOYER_REQUIREMENT in steps
    assert ConversationStep.EMPLOYER_LOCATION in steps
