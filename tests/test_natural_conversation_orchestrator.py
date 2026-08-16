from pathlib import Path

from app.repositories.conversation_observability_repository import ConversationObservabilityRepository
from app.services.natural_conversation_orchestrator import NaturalConversationOrchestrator


class Stub:
    def __init__(self, reply=None, error=None):
        self.reply = reply
        self.error = error
        self.calls = []

    def process(self, sender, message):
        self.calls.append((sender, message))
        if self.error:
            raise self.error
        return self.reply


def test_detects_ride_from_natural_telugu():
    domain, confidence = NaturalConversationOrchestrator.detect_domain(
        "హాయ్ PODX విజయవాడ నుంచి హైదరాబాద్ రైడ్ కావాలి రెండు సీట్లు"
    )
    assert domain == "RIDE"
    assert confidence >= 0.75


def test_confident_domain_handler_gets_first_chance(tmp_path: Path):
    repo = ConversationObservabilityRepository(str(tmp_path / "obs.db"))
    ride = Stub("ride handled")
    delegate = Stub("delegate handled")
    service = NaturalConversationOrchestrator(delegate, repo, {"RIDE": ride})

    reply = service.process("u1", "I need a ride, one seat")

    assert reply == "ride handled"
    assert len(ride.calls) == 1
    assert delegate.calls == []
    assert repo.summary()["total"] == 1


def test_unhandled_domain_falls_back_to_existing_stack(tmp_path: Path):
    repo = ConversationObservabilityRepository(str(tmp_path / "obs.db"))
    ride = Stub(None)
    delegate = Stub("existing flow")
    service = NaturalConversationOrchestrator(delegate, repo, {"RIDE": ride})

    assert service.process("u1", "ride కావాలి") == "existing flow"
    assert len(ride.calls) == 1
    assert len(delegate.calls) == 1


def test_handler_exception_does_not_lose_message(tmp_path: Path):
    repo = ConversationObservabilityRepository(str(tmp_path / "obs.db"))
    ride = Stub(error=RuntimeError("boom"))
    delegate = Stub("fallback safe")
    service = NaturalConversationOrchestrator(delegate, repo, {"RIDE": ride})

    assert service.process("u1", "ride కావాలి") == "fallback safe"
    summary = repo.summary()
    assert summary["errors"] == 1
    assert summary["total"] == 2


def test_delegate_exception_returns_safe_reference(tmp_path: Path):
    repo = ConversationObservabilityRepository(str(tmp_path / "obs.db"))
    service = NaturalConversationOrchestrator(Stub(error=ValueError("bad")), repo)

    reply = service.process("u1", "something unusual")

    assert "temporary issue" in reply
    assert "Ref:" in reply
    assert repo.summary()["errors"] == 1


def test_none_reply_is_recorded_unresolved(tmp_path: Path):
    repo = ConversationObservabilityRepository(str(tmp_path / "obs.db"))
    service = NaturalConversationOrchestrator(Stub(None), repo)

    reply = service.process("u1", "completely new request phrase")

    assert "detail" in reply
    assert repo.summary()["unresolved"] == 1
    assert len(repo.unresolved()) == 1


def test_ambiguous_single_term_does_not_force_handler(tmp_path: Path):
    repo = ConversationObservabilityRepository(str(tmp_path / "obs.db"))
    product = Stub("product forced")
    service = NaturalConversationOrchestrator(Stub("delegate"), repo, {"PRODUCT": product})

    # price is a single product signal but still a unique domain signal and safe to route.
    reply = service.process("u1", "price ఎంత")
    assert reply == "product forced"
