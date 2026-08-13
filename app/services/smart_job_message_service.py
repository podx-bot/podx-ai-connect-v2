import re


class SmartJobMessageService:
    """Extract obvious job details from one natural-language message.

    V1 deliberately uses deterministic rules only. It never invents missing
    details; callers keep the existing menu flow as a fallback.
    """

    CATEGORY_TERMS = (
        ("House Cleaning", ("house cleaning", "home cleaning", "cleaning", "క్లీనింగ్", "హౌస్ క్లీనింగ్")),
        ("AC Technician", ("ac technician", "ac repair", "ac service", "ఏసీ టెక్నీషియన్", "ఏసీ రిపేర్")),
        ("Electrician", ("electrician", "ఎలక్ట్రిషియన్")),
        ("Warehouse", ("warehouse", "వేర్ హౌస్", "వేర్‌హౌస్")),
        ("Catering", ("catering", "కేటరింగ్")),
        ("Delivery", ("delivery boy", "delivery", "డెలివరీ బాయ్", "డెలివరీ")),
        ("Driver", ("driver", "డ్రైవర్")),
        ("Hotel", ("hotel", "హోటల్")),
    )

    EXPERIENCE_TERMS = (
        ("Fresher", ("fresher", "no experience", "ఫ్రెషర్", "అనుభవం లేదు")),
        ("1-2 Years", ("1 year", "2 years", "1-2 years", "1 to 2 years", "ఒక సంవత్సరం", "రెండు సంవత్సరాలు")),
        ("3-5 Years", ("3 years", "4 years", "3-5 years", "3 to 5 years", "మూడు సంవత్సరాలు", "నాలుగు సంవత్సరాలు")),
        ("5+ Years", ("5+ years", "more than 5 years", "5 years experience", "ఐదు సంవత్సరాలు")),
    )

    AVAILABILITY_TERMS = (
        ("Tomorrow", ("tomorrow", "రేపు", "రేపటి నుంచి", "రేపటినుంచి")),
        ("This Week", ("this week", "ఈ వారం")),
        ("Today", ("today", "ఈరోజు", "ఇవాళ", "ఇప్పుడే", "వెంటనే")),
    )

    def extract(self, message: str) -> dict:
        text = " ".join(str(message or "").strip().split())
        lowered = text.lower()
        return {
            "category": self._first_match(lowered, self.CATEGORY_TERMS),
            "experience": self._first_match(lowered, self.EXPERIENCE_TERMS),
            "availability": self._first_match(lowered, self.AVAILABILITY_TERMS),
            "required_workers": self._extract_worker_count(lowered),
            "requirement": text,
        }

    @staticmethod
    def _first_match(text: str, groups) -> str | None:
        for label, terms in groups:
            if any(term in text for term in terms):
                return label
        return None

    @staticmethod
    def _extract_worker_count(text: str) -> int | None:
        patterns = (
            r"\b(\d{1,3})\s*(?:workers?|staff|people|persons?)\b",
            r"\b(\d{1,3})\s*(?:వర్కర్స్|వర్కర్|మంది)\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                count = int(match.group(1))
                if 1 <= count <= 999:
                    return count
        return None
