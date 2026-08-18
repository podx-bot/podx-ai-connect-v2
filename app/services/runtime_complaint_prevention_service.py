"""Runtime guard that enforces global PODX complaint-prevention guarantees."""
from __future__ import annotations

from dataclasses import dataclass

from app.services.user_pain_advantage_policy import UserPainAdvantagePolicy


@dataclass
class _ConversationGuardState:
    last_reply: str = ""
    repeat_count: int = 0


class RuntimeComplaintPreventionService:
    """Wrap the final app flow with no-silent-drop and no-bot-loop protection.

    This service intentionally owns only cross-domain guarantees. Domain runtimes keep
    their own business state machines, while this guard prevents the most damaging
    UX failures from escaping to the user unchanged.
    """

    ESCALATION_THRESHOLD = 3

    def __init__(self, delegate, category_brain=None, observability_repository=None) -> None:
        self.delegate = delegate
        self.category_brain = category_brain
        self.observability = observability_repository
        self._states: dict[str, _ConversationGuardState] = {}

    def process(self, sender_mobile: str, message: str) -> str:
        sender = str(sender_mobile)
        clean = str(message or "").strip()
        domain = self._domain(clean)

        try:
            reply = self.delegate.process(sender_mobile=sender, message=clean)
        except TypeError:
            reply = self.delegate.process(sender, clean)

        text = str(reply or "").strip()
        if not text:
            self._record(sender, clean, domain, "NO_SILENT_DROP")
            return (
                "మీ request save అయింది. ఇప్పుడే పూర్తి answer ఇవ్వలేకపోయాను. "
                "PODX దీనిని unresolvedగా mark చేసి next help/contact routeకి తీసుకెళ్తుంది."
            )

        state = self._states.setdefault(sender, _ConversationGuardState())
        signature = self._normalise(text)
        if signature and signature == state.last_reply:
            state.repeat_count += 1
        else:
            state.last_reply = signature
            state.repeat_count = 1

        if state.repeat_count >= self.ESCALATION_THRESHOLD and self._looks_like_unresolved(text):
            self._record(sender, clean, domain, "BOT_LOOP_PREVENTED", {"repeat_count": state.repeat_count})
            state.repeat_count = 0
            return (
                "ఇదే step మళ్లీ మళ్లీ రావడం వల్ల నేను ఈ flowని repeat చేయను. "
                "మీ context అలాగే ఉంచి counterpart/contact లేదా human supportకి escalate చేస్తాను."
            )

        return text

    def _domain(self, message: str) -> str:
        if self.category_brain is None:
            return "GENERAL"
        try:
            result = self.category_brain.classify(message)
            return str(getattr(result, "category", "GENERAL") or "GENERAL").upper()
        except Exception:
            return "GENERAL"

    @staticmethod
    def _normalise(text: str) -> str:
        return " ".join(str(text or "").casefold().split())

    @staticmethod
    def _looks_like_unresolved(text: str) -> bool:
        value = str(text or "").casefold()
        markers = (
            "detail కావాలి",
            "మళ్లీ ప్రయత్నించండి",
            "try again",
            "need more detail",
            "unable to",
            "temporary issue",
            "చెప్పండి",
        )
        return any(marker in value for marker in markers)

    def _record(self, sender: str, message: str, domain: str, outcome: str, metadata=None) -> None:
        if self.observability is None:
            return
        try:
            self.observability.record(
                sender,
                message,
                domain,
                outcome,
                route_source="runtime_quality_guard",
                metadata={
                    "policy_rules": sorted(UserPainAdvantagePolicy.rule_keys(domain)),
                    **(metadata or {}),
                },
            )
        except Exception:
            return
