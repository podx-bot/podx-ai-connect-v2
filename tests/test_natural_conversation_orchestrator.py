from pathlib import Path

from app.repositories.conversation_observability_repository import ConversationObservabilityRepository
from app.services.natural_conversation_orchestrator import NaturalConversationOrchestrator
from app.services.universal_category_flow_brain import UniversalCategoryFlowBrain


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


def test_category_brain_routes_counted_worker_hire_to_job_handler(tmp_path: Path):
    repo = ConversationObservabilityRepository(str(tmp_path / "obs.db"))
    job = Stub("job handled")
    delegate = Stub("delegate handled")
    service = NaturalConversationOrchestrator(
        delegate,
        repo,
        {"JOB": job},
        category_brain=UniversalCategoryFlowBrain(),
    )

    assert service.process("u1", "need 3 workers for warehouse") == "job handled"
    assert len(job.calls) == 1
    assert delegate.calls == []


def test_category_brain_specific_service_beats_generic_kavali(tmp_path: Path):
    repo = ConversationObservabilityRepository(str(tmp_path / "obs.db"))
    service_handler = Stub("service handled")
    product_handler = Stub("product wrong")
    delegate = Stub("delegate")
    service = NaturalConversationOrchestrator(
        delegate,
        repo,
        {"SERVICE": service_handler, "PRODUCT": product_handler},
        category_brain=UniversalCategoryFlowBrain(),
    )

    assert service.process("u1", "AC repair కావాలి") == "service handled"
    assert len(service_handler.calls) == 1
    assert product_handler.calls == []


def test_platform_kyc_command_keeps_priority_over_business_brain(tmp_path: Path):
    repo = ConversationObservabilityRepository(str(tmp_path / "obs.db"))
    kyc = Stub("kyc handled")
    delegate = Stub("delegate")
    service = NaturalConversationOrchestrator(
        delegate,
        repo,
        {"KYC": kyc},
        category_brain=UniversalCategoryFlowBrain(),
    )

    assert service.process("u1", "driving license upload చేయాలి") == "kyc handled"
    assert len(kyc.calls) == 1


def test_unhandled_category_falls_back_to_existing_stack(tmp_path: Path):
    repo = ConversationObservabilityRepository(str(tmp_path / "obs.db"))
    delegate = Stub("existing flow")
    service = NaturalConversationOrchestrator(
        delegate,
        repo,
        {"PRODUCT": Stub("product")},
        category_brain=UniversalCategoryFlowBrain(),
    )

    assert service.process("u1", "hotel room booking కావాలి") == "existing flow"
    assert len(delegate.calls) == 1


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

    reply = service.process("u1", "price ఎంత")
    assert reply == "product forced"
