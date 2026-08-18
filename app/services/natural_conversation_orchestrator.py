"""Single natural-language routing layer for PODX modules with safe fallbacks."""
from __future__ import annotations

import re
from typing import Any


class NaturalConversationOrchestrator:
    """Route confident requests once, then fall back to the established stack.

    The UniversalCategoryFlowBrain is the primary classifier for business domains.
    Legacy pattern detection remains only for platform-specific commands such as KYC,
    PODX Meet and Ledger, and as a compatibility fallback when the category brain is
    not supplied. Runtime errors are contained so a single module cannot lose a
    WhatsApp message.
    """

    CATEGORY_TO_HANDLER = {
        "MOBILITY": "RIDE",
        "EVENT": "EVENT",
        "APPOINTMENT": "APPOINTMENT",
        "JOBS": "JOB",
        "COMMERCE": "PRODUCT",
        "SERVICES": "SERVICE",
    }

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

    PLATFORM_DOMAINS = {"KYC", "MEET", "LEDGER"}
    WAKE_PREFIXES = (
        r"^hi\s+podx[\s,.:;-]*", r"^hey\s+podx[\s,.:;-]*", r"^hello\s+podx[\s,.:;-]*",
        r"^హాయ్\s+(?:podx|పోడక్స్|పోడెక్స్)[\s,.:;-]*", r"^హలో\s+(?:podx|పోడక్స్|పోడెక్స్)[\s,.:;-]*",
    )

    def __init__(
        self,
        delegate,
        observability_repository=None,
        handlers: dict[str, Any] | None = None,
        category_brain=None,
    ) -> None:
        self.delegate = delegate
        self.observability = observability_repository
        self.handlers = {str(k).upper(): v for k, v in (handlers or {}).items() if v is not None}
        self.category_brain = category_brain

    def process(self, sender_mobile: str, message: str) -> str:
        clean = " ".join(str(message or "").strip().split())
        domain, confidence, metadata = self._route(clean)

        handler = self.handlers.get(domain) if confidence >= 0.75 else None
        if handler is not None:
            try:
                reply = self._call(handler, sender_mobile, clean)
                if reply is not None:
                    self._record(sender_mobile, clean, domain, "HANDLED", "domain_handler", metadata=metadata)
                    return str(reply)
            except Exception as error:
                self._record(
                    sender_mobile, clean, domain, "ERROR", "domain_handler",
                    error_type=type(error).__name__, metadata=metadata,
                )

        try:
            reply = self._call(self.delegate, sender_mobile, clean)
        except Exception as error:
            incident_id = self._record(
                sender_mobile, clean, domain, "ERROR", "delegate", error_type=type(error).__name__,
                metadata=metadata,
            )
            suffix = f" Ref: {incident_id}." if incident_id else ""
            return "ఈ request process చేస్తుండగా temporary issue వచ్చింది. మీ message save అయింది; మళ్లీ ప్రయత్నించండి." + suffix

        if reply is None or not str(reply).strip():
            incident_id = self._record(
                sender_mobile, clean, domain, "UNRESOLVED", "delegate", metadata=metadata,
            )
            suffix = f" Ref: {incident_id}." if incident_id else ""
            return (
                "మీ request అర్థం చేసుకోవడానికి ఇంకొంచెం detail కావాలి. మీకు కావాల్సింది మీ మాటల్లో చెప్పండి—"
                "product, service, job, appointment, ride లేదా event ఏదైనా సరే." + suffix
            )

        self._record(sender_mobile, clean, domain, "HANDLED", "delegate", metadata=metadata)
        return str(reply)

    def _route(self, message: str) -> tuple[str, float, dict[str, Any]]:
        platform_domain, platform_confidence = self.detect_domain(message, allowed_domains=self.PLATFORM_DOMAINS)
        if platform_confidence >= 0.75:
            return platform_domain, platform_confidence, {
                "confidence": platform_confidence,
                "classifier": "platform_rules",
            }

        if self.category_brain is not None:
            try:
                decision = self.category_brain.classify(self._strip_wake_prefix(message))
                category = str(getattr(decision, "category", "GENERAL") or "GENERAL").upper()
                confidence = float(getattr(decision, "confidence", 0.0) or 0.0)
                handler_domain = self.CATEGORY_TO_HANDLER.get(category)
                metadata = {
                    "confidence": confidence,
                    "classifier": "category_brain",
                    "category": category,
                    "side": str(getattr(decision, "side", "UNKNOWN")),
                    "action": str(getattr(decision, "action", "UNKNOWN")),
                }
                if handler_domain:
                    return handler_domain, confidence, metadata
                return category, confidence, metadata
            except Exception:
                pass

        domain, confidence = self.detect_domain(message)
        return domain, confidence, {"confidence": confidence, "classifier": "legacy_rules"}

    @classmethod
    def _strip_wake_prefix(cls, message: str) -> str:
        text = str(message or "").casefold().strip()
        for pattern in cls.WAKE_PREFIXES:
            text = re.sub(pattern, "", text, count=1).strip()
        return text

    @classmethod
    def detect_domain(cls, message: str, allowed_domains: set[str] | None = None) -> tuple[str, float]:
        text = cls._strip_wake_prefix(message)
        if not text:
            return "UNKNOWN", 0.0

        patterns = cls.DOMAIN_PATTERNS
        if allowed_domains is not None:
            patterns = {key: value for key, value in patterns.items() if key in allowed_domains}
        if not patterns:
            return "UNKNOWN", 0.0

        scores = {domain: sum(1 for term in terms if term in text) for domain, terms in patterns.items()}
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
