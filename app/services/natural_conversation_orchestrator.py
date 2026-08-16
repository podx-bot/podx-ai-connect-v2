"""Single natural-language routing layer for PODX modules with safe fallbacks."""
from __future__ import annotations

import re
from typing import Any, Callable


class NaturalConversationOrchestrator:
    """Route obvious domain requests once, then fall back to the existing conversation stack.

    The orchestrator is deliberately compatibility-first: it does not replace module-specific
    state machines. It gives a confident domain handler first chance, otherwise delegates to
    the existing full stack. Runtime errors are contained and recorded instead of breaking the
    WhatsApp reply path.
    """

    DOMAIN_PATTERNS = {
        "RIDE": (
            "ride", "carpool", "car pool", "seat", "సీటు", "సీట్లు", "రైడ్", "కార్ పూల్",
            "pickup", "drop", "డ్రైవర్ రైడ్",
        ),
        "KYC": (
            "kyc", "driving licence", "driving license", "dl ", "rc ", "insurance",
            "vehicle photo", "డ్రైవింగ్ లైసెన్స్", "ఇన్సూరెన్స్", "వాహనం", "ఆర్సీ",
        ),
        "MEET": ("podx meet", "meet create", "meet join", "meet leave", "local meet", "మీట్"),
        "EVENT": (
            "event", "function", "wedding", "marriage", "birthday", "catering", "caterer",
            "decoration", "photography", "hall", "flowers", "sound", "ఫంక్షన్", "కేటరింగ్",
            "వెడ్డింగ్", "పెళ్లి", "డెకరేషన్",
        ),
        "LEDGER": (
            "ledger", "khata", "ఖాతా", "బాకీ", "balance", "received", "paid", "payable",
            "receivable", "తీసుకున్నా", "ఇచ్చాను", "చెల్లించాను",
        ),
        "APPOINTMENT": (
            "appointment", "doctor booking", "salon booking", "clinic booking", "hospital appointment",
            "అపాయింట్మెంట్", "డాక్టర్ బుకింగ్", "సెలూన్ బుకింగ్",
        ),
        "JOB": (
            "job", "worker", "workers", "staff", "ఉద్యోగం", "జాబ్", "పని కావాలి",
            "వర్కర్", "వర్కర్స్", "స్టాఫ్", "నౌకరీ", "नौकरी", "कर्मचारी",
        ),
        "PRODUCT": (
            "product", "buy", "sell", "price", "stock", "shop", "seller", "కొనాలి", "అమ్మాలి",
            "ధర", "స్టాక్", "ప్రోడక్ట్", "ప్రొడక్ట్",
        ),
        "SERVICE": (
            "service", "electrician", "plumber", "tailor", "carpenter", "mechanic", "repair",
            "సర్వీస్", "ఎలక్ట్రిషియన్", "ప్లంబర్", "టైలర్", "కార్పెంటర్", "మెకానిక్",
        ),
    }

    WAKE_PREFIXES = (
        r"^hi\s+podx[\s,.:;-]*", r"^hey\s+podx[\s,.:;-]*", r"^hello\s+podx[\s,.:;-]*",
        r"^హాయ్\s+(?:podx|పోడక్స్|పోడెక్స్)[\s,.:;-]*", r"^హలో\s+(?:podx|పోడక్స్|పోడెక్స్)[\s,.:;-]*",
    )

    def __init__(self, delegate, observability_repository=None, handlers: dict[str, Any] | None = None) -> None:
        self.delegate = delegate
        self.observability = observability_repository
        self.handlers = {str(k).upper(): v for k, v in (handlers or {}).items() if v is not None}

    def process(self, sender_mobile: str, message: str) -> str:
        clean = " ".join(str(message or "").strip().split())
        domain, confidence = self.detect_domain(clean)

        handler = self.handlers.get(domain) if confidence >= 0.75 else None
        if handler is not None:
            try:
                reply = self._call(handler, sender_mobile, clean)
                if reply is not None:
                    self._record(sender_mobile, clean, domain, "HANDLED", "domain_handler", metadata={"confidence": confidence})
                    return str(reply)
            except Exception as error:
                self._record(
                    sender_mobile, clean, domain, "ERROR", "domain_handler",
                    error_type=type(error).__name__, metadata={"confidence": confidence},
                )
                # Continue through the established stack; a single module failure should not lose the message.

        try:
            reply = self._call(self.delegate, sender_mobile, clean)
        except Exception as error:
            incident_id = self._record(
                sender_mobile, clean, domain, "ERROR", "delegate", error_type=type(error).__name__,
                metadata={"confidence": confidence},
            )
            suffix = f" Ref: {incident_id}." if incident_id else ""
            return "ఈ request process చేస్తుండగా temporary issue వచ్చింది. మీ message save అయింది; మళ్లీ ప్రయత్నించండి." + suffix

        if reply is None or not str(reply).strip():
            incident_id = self._record(
                sender_mobile, clean, domain, "UNRESOLVED", "delegate", metadata={"confidence": confidence},
            )
            suffix = f" Ref: {incident_id}." if incident_id else ""
            return (
                "మీ request అర్థం చేసుకోవడానికి ఇంకొంచెం detail కావాలి. మీకు కావాల్సింది మీ మాటల్లో చెప్పండి—"
                "product, service, job, appointment, ride లేదా event ఏదైనా సరే." + suffix
            )

        self._record(sender_mobile, clean, domain, "HANDLED", "delegate", metadata={"confidence": confidence})
        return str(reply)

    @classmethod
    def detect_domain(cls, message: str) -> tuple[str, float]:
        text = str(message or "").casefold().strip()
        for pattern in cls.WAKE_PREFIXES:
            text = re.sub(pattern, "", text, count=1).strip()
        if not text:
            return "UNKNOWN", 0.0

        scores: dict[str, int] = {}
        for domain, terms in cls.DOMAIN_PATTERNS.items():
            scores[domain] = sum(1 for term in terms if term in text)
        best = max(scores, key=scores.get)
        best_score = scores[best]
        if best_score <= 0:
            return "UNKNOWN", 0.0
        ties = sum(1 for score in scores.values() if score == best_score)
        confidence = 0.95 if best_score >= 2 else (0.8 if ties == 1 else 0.6)
        return best, confidence

    @staticmethod
    def _call(target, sender_mobile: str, message: str):
        process = getattr(target, "process", None)
        if callable(process):
            return process(sender_mobile, message)
        if callable(target):
            return target(sender_mobile, message)
        return None

    def _record(
        self,
        sender_mobile: str,
        message: str,
        domain: str,
        outcome: str,
        route_source: str,
        error_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int | None:
        if self.observability is None:
            return None
        try:
            return int(self.observability.record(
                sender_mobile, message, domain, outcome,
                route_source=route_source, error_type=error_type, metadata=metadata,
            ))
        except Exception:
            return None
