import re
from typing import Any

from google import genai


class IntentRouterService:
    """Classify free-form PODX requests into stable product intents.

    Fast keyword rules handle common requests without an AI round trip. Gemini is
    used only as a fallback for genuinely ambiguous phrasing. One client is reused
    for fallback calls so connection setup is not paid on every message.
    """

    SUPPORTED_INTENTS = {
        "JOB_SEEKER",
        "EMPLOYER",
        "PROFILE",
        "HELP",
        "APPOINTMENT",
        "SERVICE",
        "SERVICE_PROVIDER",
        "SHOP_PRODUCT",
        "SELL_PRODUCT",
        "GREETING",
        "UNKNOWN",
    }

    def __init__(self, api_key: str, model: str = "gemini-3.6-flash") -> None:
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "").strip() or "gemini-3.6-flash"
        self._client = genai.Client(api_key=self.api_key) if self.api_key else None
        self._last_classification_text: str | None = None
        self._last_classification_result: dict[str, Any] | None = None

    def classify(self, message: str) -> dict[str, Any]:
        text = " ".join(str(message or "").strip().split())
        if not text:
            return {"intent": "UNKNOWN", "source": "empty", "confidence": 0.0}

        if text == self._last_classification_text and self._last_classification_result is not None:
            return dict(self._last_classification_result)

        rule_intent = self._classify_rules(text)
        if rule_intent:
            return self._remember_classification(
                text,
                {"intent": rule_intent, "source": "rules", "confidence": 1.0},
            )

        if self._client is None:
            return self._remember_classification(
                text,
                {"intent": "UNKNOWN", "source": "no_ai_key", "confidence": 0.0},
            )

        prompt = (
            "Classify this PODX user request into exactly one intent. "
            "Return only one label, no punctuation or explanation.\n"
            "Labels: JOB_SEEKER, EMPLOYER, PROFILE, HELP, APPOINTMENT, SERVICE, "
            "SERVICE_PROVIDER, SHOP_PRODUCT, SELL_PRODUCT, GREETING, UNKNOWN.\n"
            "JOB_SEEKER = user wants a job/work. EMPLOYER = user wants workers/staff. "
            "APPOINTMENT = doctor/salon/clinic booking. SERVICE = user needs an electrician, "
            "plumber, tailor/alteration, carpenter, repair, cleaning or other local service. "
            "SERVICE_PROVIDER = user offers/provides a local service. SHOP_PRODUCT = user wants "
            "to buy/find/check price or stock of a product. SELL_PRODUCT = user sells/offers/has "
            "products for customers. Preserve meaning across Indian languages and mixed speech. "
            "Ignore wake words such as Hi PODX/Hey PODX when deciding the actual request. "
            "A specific profession/service request such as 'electrician కావాలి' or "
            "'alteration కావాలి' is SERVICE unless the user explicitly says they want workers/staff.\n\n"
            f"Request: {text}"
        )
        try:
            interaction = self._client.interactions.create(
                model=self.model,
                input=prompt,
                store=False,
            )
            label = str(getattr(interaction, "output_text", "") or "").strip().upper()
            label = re.sub(r"[^A-Z_]", "", label)
            if label in self.SUPPORTED_INTENTS:
                return self._remember_classification(
                    text,
                    {"intent": label, "source": "gemini", "confidence": 0.8},
                )
        except Exception as error:
            return self._remember_classification(
                text,
                {
                    "intent": "UNKNOWN",
                    "source": "gemini_error",
                    "confidence": 0.0,
                    "error_type": type(error).__name__,
                },
            )

        return self._remember_classification(
            text,
            {"intent": "UNKNOWN", "source": "gemini_unknown", "confidence": 0.0},
        )

    def _remember_classification(self, text: str, result: dict[str, Any]) -> dict[str, Any]:
        self._last_classification_text = text
        self._last_classification_result = dict(result)
        return dict(result)

    @staticmethod
    def _normalize_for_rules(text: str) -> str:
        lowered = " ".join(str(text or "").lower().split())
        wake_patterns = (
            r"^hi\s+podx[\s,.:;-]*",
            r"^hey\s+podx[\s,.:;-]*",
            r"^hello\s+podx[\s,.:;-]*",
            r"^హాయ్\s+(?:podx|పోడక్స్|పోడెక్స్|ప్రోడక్స్)[\s,.:;-]*",
            r"^హలో\s+(?:podx|పోడక్స్|పోడెక్స్|ప్రోడక్స్)[\s,.:;-]*",
        )
        for pattern in wake_patterns:
            lowered = re.sub(pattern, "", lowered, count=1).strip()
        return lowered

    @staticmethod
    def _classify_rules(text: str) -> str | None:
        lowered = IntentRouterService._normalize_for_rules(text)

        greeting_terms = {"hi", "hello", "hey", "హాయ్", "హలో", "नमस्ते", "हाय"}
        if lowered in greeting_terms:
            return "GREETING"

        if any(term in lowered for term in ("నా ప్రొఫైల్", "my profile", "profile చూప", "मेरी प्रोफाइल")):
            return "PROFILE"
        if any(term in lowered for term in ("help", "సహాయం", "హెల్ప్", "मदद")):
            return "HELP"

        appointment_terms = (
            "appointment", "అపాయింట్మెంట్", "doctor booking", "డాక్టర్ బుకింగ్",
            "salon booking", "సెలూన్ బుకింగ్", "clinic booking", "hospital appointment",
        )
        if any(term in lowered for term in appointment_terms):
            return "APPOINTMENT"

        job_terms = (
            "ఉద్యోగం కావాలి", "పని కావాలి", "జాబ్ కావాలి", "job కావాలి",
            "need a job", "looking for job", "looking for work", "work కావాలి",
            "నాకు పని", "నాకు జాబ్", "नौकरी चाहिए",
        )
        if any(term in lowered for term in job_terms):
            return "JOB_SEEKER"

        employer_terms = (
            "workers కావాలి", "worker కావాలి", "వర్కర్స్ కావాలి", "staff కావాలి",
            "మనుషులు కావాలి", "need workers", "need staff", "hire workers",
            "कर्मचारी चाहिए", "workers required", "delivery boy కావాలి",
            "డెలివరీ బాయ్ కావాలి",
        )
        if any(term in lowered for term in employer_terms):
            return "EMPLOYER"

        service_provider_terms = (
            "service ఇస్తాను", "service చేస్తాను", "services ఇస్తాను", "services చేస్తాను",
            "సర్వీస్ ఇస్తాను", "సర్వీస్ చేస్తాను", "సేవ ఇస్తాను", "సేవలు ఇస్తాను",
            "నేను electrician", "నేను ఎలక్ట్రిషియన్", "నేను ఎలక్ట్రీషియన్",
            "నేను plumber", "నేను ప్లంబర్", "నేను tailor", "నేను టైలర్",
            "నేను carpenter", "నేను కార్పెంటర్", "నేను painter", "నేను పెయింటర్",
            "i provide service", "i provide services", "i offer service", "service provider",
            "काम करता हूँ", "सेवा देता हूँ",
        )
        if any(term in lowered for term in service_provider_terms):
            return "SERVICE_PROVIDER"

        seller_terms = (
            "అమ్ముతాను", "అమ్ముతున్నాను", "అమ్మాలి", "విక్రయిస్తాను", "సేల్ చేస్తాను",
            "నేను seller", "seller ని", "products అమ్ముతాను", "product అమ్ముతాను",
            "i sell", "we sell", "selling products", "sell products", "seller",
            "बेचता हूँ", "बेचती हूँ", "बेचना है",
        )
        if any(term in lowered for term in seller_terms):
            return "SELL_PRODUCT"

        service_terms = (
            "electrician", "electrican", "electriction", "electrition", "electrician service",
            "ఎలక్ట్రిషియన్", "ఎలక్ట్రిషన్", "ఎలక్ట్రీషియన్", "ఎలక్ట్రీషన్",
            "ఎలక్ట్రిషియ‌న్", "ఎలక్ట్రీషియ‌న్", "ఎలక్ట్రిక్ పని", "ఎలక్ట్రికల్ పని",
            "plumber", "plumbing", "ప్లంబర్", "ప్లంబింగ్",
            "ac technician", "ac repair", "ac service", "ఏసీ టెక్నీషియన్", "ఏసీ రిపేర్",
            "house cleaning", "home cleaning", "cleaning service", "క్లీనింగ్ సర్వీస్",
            "tailor", "tailoring", "alteration", "alterations", "dress alteration",
            "blouse alteration", "pant alteration", "shirt alteration", "stitching",
            "టైలర్", "టైలరింగ్", "అల్టరేషన్", "ఆల్టరేషన్", "అల్టరేషన్స్", "కుట్టు పని",
            "carpenter", "carpentry", "కార్పెంటర్", "వడ్రంగి", "painter", "painting service",
            "పెయింటర్", "పెయింటింగ్", "mechanic", "మెకానిక్", "repair person",
            "service కావాలి", "సర్వీస్ కావాలి", "సేవ కావాలి", "need service",
        )
        if any(term in lowered for term in service_terms):
            return "SERVICE"

        # STT engines sometimes produce a close electrician spelling. This bounded
        # stem is deliberately checked only after provider/employer rules above.
        if any(stem in lowered for stem in ("ఎలక్ట్రిష", "ఎలక్ట్రీష", "electrici", "electri")):
            return "SERVICE"

        driver_service_terms = (
            "driver కావాలి", "డ్రైవర్ కావాలి", "need driver", "cab driver కావాలి",
        )
        if any(term in lowered for term in driver_service_terms):
            return "SERVICE"

        product_terms = (
            "price ఎంత", "ధర ఎంత", "product కావాలి", "కొనాలి", "shop ఎక్కడ",
            "nearby shop", "buy product", "price of", "దొరుకుతుందా", "స్టాక్ ఉందా",
            "stock ఉందా", "दाम", "खरीदना",
        )
        if any(term in lowered for term in product_terms):
            return "SHOP_PRODUCT"

        return None
