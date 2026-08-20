from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class BrainResult:
    provider: str
    answer: str
    confidence: float
    success: bool = True
    reason: str = ""


class MultiBrainReliabilityService:
    """Provider-agnostic failover and verification coordinator.

    PODX-owned state stays outside model providers. This service only receives the
    normalized task/context and selects the first reliable provider result. Optional
    verifier providers can reject a low-confidence or contradictory primary result.
    """

    def __init__(
        self,
        providers: Iterable[tuple[str, Callable[[dict], BrainResult]]],
        *,
        min_confidence: float = 0.72,
        verifier: Callable[[dict, BrainResult], bool] | None = None,
    ):
        self.providers = list(providers)
        self.min_confidence = max(0.0, min(float(min_confidence), 1.0))
        self.verifier = verifier

    def run(self, task: dict) -> dict:
        attempts: list[dict] = []
        for provider_name, provider in self.providers:
            try:
                result = provider(task)
            except Exception as exc:
                attempts.append(
                    {
                        "provider": provider_name,
                        "success": False,
                        "reason": f"exception:{type(exc).__name__}",
                    }
                )
                continue

            confidence = max(0.0, min(float(result.confidence), 1.0))
            accepted = bool(result.success and result.answer.strip() and confidence >= self.min_confidence)
            verified = None
            if accepted and self.verifier is not None:
                try:
                    verified = bool(self.verifier(task, result))
                except Exception:
                    verified = False
                accepted = accepted and verified

            attempts.append(
                {
                    "provider": provider_name,
                    "success": bool(result.success),
                    "confidence": confidence,
                    "verified": verified,
                    "accepted": accepted,
                    "reason": result.reason,
                }
            )

            if accepted:
                return {
                    "status": "ANSWERED",
                    "provider": provider_name,
                    "answer": result.answer.strip(),
                    "confidence": confidence,
                    "attempts": attempts,
                }

        return {
            "status": "FALLBACK_REQUIRED",
            "provider": None,
            "answer": None,
            "confidence": 0.0,
            "attempts": attempts,
        }
