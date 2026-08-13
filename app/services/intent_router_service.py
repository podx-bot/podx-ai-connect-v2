import re
from typing import Any

from google import genai


class IntentRouterService:
    """Classify free-form PODX requests into stable product intents.

    Fast keyword rules handle common requests without an AI round trip. Gemini is
    used only as a fallback for natural Telugu/English/Hindi phrasing. The router
    never changes user/session data; callers decide whether an intent is safe to
    execute in the current conversation step.
    """

    SUPPORTED_INTENTS = {
        "JOB_SEEKER",
        "EMPLOYER",
        "PROFILE",
        "HELP",
        "APPOINTMENT",
        "SERVICE",
        "SHOP_PRODUCT",
        "GREETING",
        "UNKNOWN",
    }

    def __init__(self, api_key: str, model: str = "gemini-3.6-flash") -> None:
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "").strip() or "gemini-3.6-flash"

    def classify(self, message: str) -> dict[str, Any]:
        text = " ".join(str(message or "").strip().split())
        if not text:
            return {"intent": "UNKNOWN", "source": "empty", "confidence": 0.0}

        rule_intent = self._classify_rules(text)
        if rule_intent:
            return {"intent": rule_intent, "source": "rules", "confidence": 1.0}

        if not self.api_key:
            return {"intent": "UNKNOWN", "source": "no_ai_key", "confidence": 0.0}

        prompt = (
            "Classify this PODX user request into exactly one intent. "
            "Return only one label, no punctuation or explanation.\n"
            "Labels: JOB_SEEKER, EMPLOYER, PROFILE, HELP, APPOINTMENT, SERVICE, "
            "SHOP_PRODUCT, GREETING, UNKNOWN.\n"
            "JOB_SEEKER = user wants a job/work. EMPLOYER = user wants workers/staff. "
            "APPOINTMENT = doctor/salon/clinic booking. SERVICE = electrician, repair, "
            "cleaning or other local service. SHOP_PRODUCT = shop/product/price/buying. "
            "Preserve meaning across Telugu, English, Hindi and mixed speech.\n\n"
            f"Request: {text}"
        )
        try:
            client = genai.Client(api_key=self.api_key)
            interaction = client.interactions.create(
                model=self.model,
                input=prompt,
                store=False,
            )
            label = str(getattr(interaction, "output_text", "") or "").strip().upper()
            label = re.sub(r"[^A-Z_]", "", label)
            if label in self.SUPPORTED_INTENTS:
                return {"intent": label, "source": "gemini", "confidence": 0.8}
        except Exception as error:
            return {
                "intent": "UNKNOWN",
                "source": "gemini_error",
                "confidence": 0.0,
                "error_type": type(error).__name__,
            }

        return {"intent": "UNKNOWN", "source": "gemini_unknown", "confidence": 0.0}

    @staticmethod
    def _classify_rules(text: str) -> str | None:
        lowered = text.lower()

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

        # Explicit requests for the user's own work win before worker-hiring
        # phrases. This prevents "delivery boy పని కావాలి" from being mistaken
        # for an employer request merely because it contains "delivery boy".
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
            "డెలివరీ బాయ్ కావాలి", "driver కావాలి", "డ్రైవర్ కావాలి",
        )
        if any(term in lowered for term in employer_terms):
            return "EMPLOYER"

        service_terms = (
            "electrician", "ఎలక్ట్రిషియన్", "plumber", "ప్లంబర్", "ac repair",
            "ac service", "cleaning service", "క్లీనింగ్ సర్వీస్", "repair person",
        )
        if any(term in lowered for term in service_terms):
            return "SERVICE"

        product_terms = (
            "price ఎంత", "ధర ఎంత", "product కావాలి", "కొనాలి", "shop ఎక్కడ",
            "nearby shop", "buy product", "price of", "दाम", "खरीदना",
        )
        if any(term in lowered for term in product_terms):
            return "SHOP_PRODUCT"

        return None
