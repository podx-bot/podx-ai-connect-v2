from types import SimpleNamespace

from app.models.session import ConversationStep
from app.services.multilingual_onboarding_service import MultilingualOnboardingService


class Sessions:
    def __init__(self, step):
        self.session = SimpleNamespace(step=step, data={})
        self.saved = []

    def get(self, sender):
        return self.session

    def save(self, sender):
        self.saved.append(sender)


class Delegate:
    def __init__(self, sessions):
        self.sessions = sessions

    def process(self, sender_mobile, message):
        if self.sessions.session.step == ConversationStep.WAITING_NAME:
            self.sessions.session.step = ConversationStep.WAITING_LANGUAGE
            return "old 3-language menu"
        return "delegated"


def test_replaces_old_three_language_prompt_after_name():
    sessions = Sessions(ConversationStep.WAITING_NAME)
    service = MultilingualOnboardingService(Delegate(sessions), sessions)

    reply = service.process("u1", "Manohar")

    assert "Indian languages" in reply
    assert "1. తెలుగు" not in reply


def test_accepts_tamil_directly_during_language_step():
    sessions = Sessions(ConversationStep.WAITING_LANGUAGE)
    service = MultilingualOnboardingService(Delegate(sessions), sessions)

    reply = service.process("u1", "தமிழ்")

    assert sessions.session.data["language"] == "Tamil"
    assert sessions.session.step == ConversationStep.WAITING_AREA
    assert "ప్రాంతం" in reply


def test_accepts_free_form_language_name_without_fixed_menu():
    sessions = Sessions(ConversationStep.WAITING_LANGUAGE)
    service = MultilingualOnboardingService(Delegate(sessions), sessions)

    service.process("u1", "Konkani")

    assert sessions.session.data["language"] == "Konkani"
    assert sessions.session.step == ConversationStep.WAITING_AREA
