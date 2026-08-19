from app.services.multi_brain_reliability_service import BrainResult, MultiBrainReliabilityService


def test_uses_primary_when_confident():
    service = MultiBrainReliabilityService([
        ("gemini", lambda task: BrainResult("gemini", "ok", 0.91)),
        ("openai", lambda task: BrainResult("openai", "backup", 0.95)),
    ])

    result = service.run({"intent": "insurance"})

    assert result["status"] == "ANSWERED"
    assert result["provider"] == "gemini"
    assert len(result["attempts"]) == 1


def test_low_confidence_falls_through_to_next_provider():
    service = MultiBrainReliabilityService([
        ("gemini", lambda task: BrainResult("gemini", "uncertain", 0.40)),
        ("openai", lambda task: BrainResult("openai", "reliable", 0.88)),
    ])

    result = service.run({"intent": "insurance"})

    assert result["provider"] == "openai"
    assert len(result["attempts"]) == 2


def test_provider_exception_does_not_break_failover():
    def broken(task):
        raise TimeoutError("provider timeout")

    service = MultiBrainReliabilityService([
        ("gemini", broken),
        ("claude", lambda task: BrainResult("claude", "recovered", 0.87)),
    ])

    result = service.run({"intent": "travel"})

    assert result["provider"] == "claude"
    assert result["attempts"][0]["success"] is False


def test_verifier_can_reject_primary_and_force_backup():
    def verifier(task, result):
        return result.provider != "gemini"

    service = MultiBrainReliabilityService(
        [
            ("gemini", lambda task: BrainResult("gemini", "possible contradiction", 0.94)),
            ("openai", lambda task: BrainResult("openai", "verified answer", 0.90)),
        ],
        verifier=verifier,
    )

    result = service.run({"intent": "loan"})

    assert result["provider"] == "openai"
    assert result["attempts"][0]["verified"] is False


def test_all_failures_return_explicit_fallback_required():
    service = MultiBrainReliabilityService([
        ("gemini", lambda task: BrainResult("gemini", "", 0.95, success=False)),
        ("openai", lambda task: BrainResult("openai", "too uncertain", 0.20)),
    ])

    result = service.run({"intent": "banking"})

    assert result["status"] == "FALLBACK_REQUIRED"
    assert result["answer"] is None
