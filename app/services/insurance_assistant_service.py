"""Universal insurance question-routing and safe explanation foundation.

This service intentionally avoids inventing policy-specific facts. It classifies the
customer's need, returns a generic educational answer when safe, and explicitly
requires verified product data before answering insurer/policy-specific questions.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InsuranceIntent:
    category: str
    topic: str
    needs_verified_product_data: bool = False
    needs_human_escalation: bool = False


class InsuranceAssistantService:
    CATEGORY_TERMS = {
        "health": ("health", "medical", "hospital", "ఆరోగ్య", "హెల్త్"),
        "life": ("life", "term", "జీవిత", "టర్మ్"),
        "motor": ("motor", "car insurance", "bike insurance", "vehicle insurance", "కార్ ఇన్సూరెన్స్", "బైక్ ఇన్సూరెన్స్"),
        "travel": ("travel insurance", "trip insurance", "ట్రావెల్ ఇన్సూరెన్స్"),
        "personal_accident": ("personal accident", "accident insurance", "యాక్సిడెంట్ ఇన్సూరెన్స్"),
        "home": ("home insurance", "property insurance", "హోమ్ ఇన్సూరెన్స్", "ప్రాపర్టీ ఇన్సూరెన్స్"),
        "business": ("business insurance", "shop insurance", "commercial insurance", "బిజినెస్ ఇన్సూరెన్స్"),
    }

    TOPIC_TERMS = {
        "premium": ("premium", "price", "cost", "ప్రీమియం", "ధర", "ఎంత"),
        "coverage": ("cover", "coverage", "benefit", "కవర్", "బెనిఫిట్"),
        "exclusions": ("exclude", "exclusion", "not covered", "కవర్ కాదు", "ఎక్స్క్లూజన్"),
        "waiting_period": ("waiting period", "వెయిటింగ్ పీరియడ్"),
        "claim": ("claim", "cashless", "reimbursement", "క్లెయిమ్", "క్యాష్‌లెస్"),
        "eligibility": ("eligible", "eligibility", "age limit", "ఎలిజిబుల్", "వయసు"),
        "documents": ("document", "documents", "kyc", "డాక్యుమెంట్", "పత్రాలు"),
        "renewal": ("renew", "renewal", "రివిన్యువల్", "రిన్యువల్"),
        "nominee": ("nominee", "నామినీ"),
        "comparison": ("compare", "comparison", "which is better", "best policy", "కంపేర్", "ఏది మంచిది"),
        "cancellation": ("cancel", "cancellation", "free look", "క్యాన్సల్"),
        "grievance": ("complaint", "grievance", "rejected", "reject", "కంప్లైంట్", "రిజెక్ట్"),
    }

    PRODUCT_SPECIFIC_MARKERS = (
        "this policy", "this plan", "ఈ పాలసీ", "ఈ ప్లాన్", "insurer", "company", "policy number",
    )

    def classify(self, message: str) -> InsuranceIntent:
        text = str(message or "").strip().lower()
        category = self._match(text, self.CATEGORY_TERMS) or "general"
        topic = self._match(text, self.TOPIC_TERMS) or "general_guidance"
        specific = any(marker in text for marker in self.PRODUCT_SPECIFIC_MARKERS)
        if topic in {"premium", "coverage", "exclusions", "waiting_period", "claim", "eligibility", "comparison"}:
            specific = specific or any(token in text for token in ("idfc", "hdfc", "icici", "lic", "star", "care", "bajaj", "tata", "max", "niva"))
        escalation = topic == "grievance"
        return InsuranceIntent(
            category=category,
            topic=topic,
            needs_verified_product_data=specific,
            needs_human_escalation=escalation,
        )

    @staticmethod
    def _match(text: str, mapping: dict[str, tuple[str, ...]]) -> str | None:
        matches: list[tuple[int, str]] = []
        for key, terms in mapping.items():
            for term in terms:
                if term in text:
                    matches.append((len(term), key))
        if not matches:
            return None
        matches.sort(key=lambda item: item[0], reverse=True)
        return matches[0][1]

    def answer(self, message: str, *, verified_product: dict | None = None) -> dict:
        intent = self.classify(message)
        if intent.needs_verified_product_data and not verified_product:
            return {
                "status": "VERIFIED_PRODUCT_DATA_REQUIRED",
                "intent": intent,
                "answer": (
                    "ఈ policy/product గురించి exact premium, coverage, exclusions, waiting period లేదా claim rules చెప్పాలంటే "
                    "verified insurer/product details కావాలి. Policy name/link/PDF పంపండి; తెలిసినది మాత్రమే explain చేస్తాను."
                ),
                "next_action": "REQUEST_VERIFIED_POLICY_SOURCE",
            }

        if intent.needs_human_escalation:
            return {
                "status": "ESCALATE_WITH_GUIDANCE",
                "intent": intent,
                "answer": (
                    "Complaint/claim rejection అయితే policy number, insurer response, claim/reference number, rejection reason, "
                    "supporting documents collect చేయాలి. ముందుగా insurer grievance channelలో raise చేసి status track చేయాలి; "
                    "resolve కాకపోతే authorised grievance/escalation routeకి పంపాలి."
                ),
                "next_action": "COLLECT_CASE_DETAILS_AND_ESCALATE",
            }

        if verified_product:
            return self._answer_from_verified_product(intent, verified_product)

        return {
            "status": "GENERIC_GUIDANCE",
            "intent": intent,
            "answer": self._generic_answer(intent.topic, intent.category),
            "next_action": "CLARIFY_ONLY_IF_NEEDED",
        }

    @staticmethod
    def _generic_answer(topic: str, category: str = "general") -> str:
        if topic == "general_guidance" and category == "health":
            return (
                "Health insurance అని అర్థమైంది ✅ అదే detail మళ్లీ అడగను. "
                "Familyకి సరైన options compare చేయడానికి ముందుగా cover చేయాల్సిన సభ్యుల సంఖ్య మరియు వారి వయసులు చెప్పండి. "
                "తర్వాత అవసరమైన missing details మాత్రమే అడుగుతాను."
            )
        if topic == "general_guidance" and category != "general":
            labels = {
                "life": "Life/Term insurance",
                "motor": "Motor insurance",
                "travel": "Travel insurance",
                "personal_accident": "Personal Accident insurance",
                "home": "Home insurance",
                "business": "Business insurance",
            }
            label = labels.get(category, "Insurance")
            return f"{label} అని అర్థమైంది ✅ అదే category మళ్లీ అడగను. ఇప్పుడు అవసరమైన missing details మాత్రమే అడుగుతాను."

        answers = {
            "premium": "Premium age, coverage amount, term, health/risk details, add-ons and insurer pricingపై మారుతుంది. Exact quote కోసం customer details + verified product quote అవసరం.",
            "coverage": "Coverage అంటే policyలో insurer pay/protect చేసే insured events/benefits. Sum insured, sub-limits, waiting periods and exclusionsతో కలిసి చూడాలి.",
            "exclusions": "Exclusions అంటే policy pay చేయని situations. Final decision ముందు exclusions, limits, waiting periods మరియు special conditions చదవాలి.",
            "waiting_period": "Waiting periodలో కొన్ని benefits/conditionsకి claim eligibility వెంటనే ఉండకపోవచ్చు. Exact duration policy wordingలో verify చేయాలి.",
            "claim": "Claim flow సాధారణంగా incident/treatment notification, required documents, insurer/TPA review, approval/rejection and settlementగా ఉంటుంది. Cashless availability network/provider rulesపై ఆధారపడుతుంది.",
            "eligibility": "Eligibility age, occupation, health, location, sum insured and product rulesపై ఆధారపడుతుంది. Exact acceptance insurer underwriting నిర్ణయిస్తుంది.",
            "documents": "Commonly identity/address, proposal details and product-specific supporting documents అవసరం కావచ్చు. Exact checklist insurer/product ప్రకారం verify చేయాలి.",
            "renewal": "Renewal ముందు premium change, coverage continuity, waiting-period credit, add-ons and policy changes verify చేయాలి.",
            "nominee": "Nominee details currentగా ఉంచడం మంచిది. Nomination process and legal effect product type/policy rulesపై ఆధారపడుతుంది.",
            "comparison": "Policies compare చేసేప్పుడు premium ఒక్కటే కాదు: coverage, exclusions, waiting periods, sub-limits, claim process, network/support and policy conditions చూడాలి.",
            "cancellation": "Cancellation/free-look rules product and policy termsపై ఆధారపడతాయి. Purchase date, policy wording and applicable charges/refund rules verify చేయాలి.",
            "general_guidance": "మీకు ఏ insurance కావాలో చెప్పండి—Health, Life/Term, Motor, Travel, Personal Accident, Home లేదా Business. నేను అవసరమైన details మాత్రమే అడిగి options explain చేస్తాను.",
        }
        return answers.get(topic, answers["general_guidance"])

    @staticmethod
    def _answer_from_verified_product(intent: InsuranceIntent, product: dict) -> dict:
        topic = intent.topic
        field_map = {
            "premium": "premium",
            "coverage": "coverage",
            "exclusions": "exclusions",
            "waiting_period": "waiting_period",
            "claim": "claim_process",
            "eligibility": "eligibility",
            "documents": "documents",
            "renewal": "renewal",
            "nominee": "nominee",
            "cancellation": "cancellation",
        }
        field = field_map.get(topic)
        value = product.get(field) if field else None
        if value:
            return {
                "status": "VERIFIED_PRODUCT_ANSWER",
                "intent": intent,
                "answer": str(value),
                "source": product.get("source"),
                "next_action": "ANSWERED_FROM_VERIFIED_SOURCE",
            }
        return {
            "status": "VERIFIED_FIELD_MISSING",
            "intent": intent,
            "answer": "Verified product dataలో ఈ detail లేదు. Guess చేయకుండా insurer/source నుంచి verify చేయాలి.",
            "source": product.get("source"),
            "next_action": "VERIFY_MISSING_FIELD",
        }
