import re


class SmartJobMessageService:
    """Extract structured job-lead details from natural Telugu/English speech.

    Deterministic normalization handles common spoken variants without inventing
    missing values. The conversation layer asks only for fields that remain empty.
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
        ("Fresher", ("fresher", "no experience", "ఫ్రెషర్", "అనుభవం లేదు", "experience లేదు")),
        ("1-2 Years", (
            "1 year", "2 years", "1-2 years", "1 to 2 years",
            "ఒక సంవత్సరం", "ఒక సంవత్సర", "ఒక ఏడాది", "ఏడాది experience",
            "రెండు సంవత్సరాలు", "రెండు సంవత్సరాల", "రెండేళ్లు", "రెండేళ్ల",
        )),
        ("3-5 Years", (
            "3 years", "4 years", "3-5 years", "3 to 5 years",
            "మూడు సంవత్సరాలు", "మూడు సంవత్సరాల", "మూడేళ్లు", "మూడేళ్ల",
            "నాలుగు సంవత్సరాలు", "నాలుగు సంవత్సరాల", "నాలుగేళ్లు", "నాలుగేళ్ల",
        )),
        ("5+ Years", (
            "5+ years", "more than 5 years", "5 years experience",
            "ఐదు సంవత్సరాలు", "ఐదు సంవత్సరాల", "ఐదేళ్లు", "ఐదేళ్ల",
        )),
    )

    AVAILABILITY_TERMS = (
        ("Tomorrow", ("tomorrow", "రేపు", "రేపటి నుంచి", "రేపటినుంచి", "రేపటి నుండి", "రేపటినుండి")),
        ("This Week", ("this week", "ఈ వారం", "ఈ వారంలో", "వారం లోపల")),
        ("Today", ("today", "ఈరోజు", "ఈ రోజు", "ఇవాళ", "ఇప్పుడే", "వెంటనే", "ఈరోజు నుంచి", "ఈరోజు నుండి")),
    )

    TELUGU_EXPERIENCE_NUMBERS = {
        "ఒక": 1,
        "ఒక్క": 1,
        "రెండు": 2,
        "మూడు": 3,
        "నాలుగు": 4,
        "ఐదు": 5,
        "ఆరు": 6,
        "ఏడు": 7,
        "ఎనిమిది": 8,
        "తొమ్మిది": 9,
        "పది": 10,
    }

    TELUGU_WORKER_COUNTS = {
        "ఒకరు": 1,
        "ఒక్కరు": 1,
        "ఇద్దరు": 2,
        "ముగ్గురు": 3,
        "నలుగురు": 4,
        "ఐదుగురు": 5,
        "ఆరుగురు": 6,
        "ఏడుగురు": 7,
        "ఎనిమిది మంది": 8,
        "తొమ్మిది మంది": 9,
        "పది మంది": 10,
    }

    def extract(self, message: str) -> dict:
        text = " ".join(str(message or "").strip().split())
        lowered = text.lower()
        return {
            "category": self._first_match(lowered, self.CATEGORY_TERMS),
            "experience": self._extract_experience(lowered),
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

    def _extract_experience(self, text: str) -> str | None:
        direct = self._first_match(text, self.EXPERIENCE_TERMS)
        if direct:
            return direct

        numeric = re.search(r"\b(\d{1,2})\s*(?:years?|yrs?|yr)\b", text, flags=re.IGNORECASE)
        if numeric:
            return self._experience_bucket(int(numeric.group(1)))

        for word, years in self.TELUGU_EXPERIENCE_NUMBERS.items():
            patterns = (
                f"{word} సంవత్సరం",
                f"{word} సంవత్సర",
                f"{word} ఏళ్లు",
                f"{word} ఏళ్ల",
                f"{word} యేళ్లు",
                f"{word} యేళ్ల",
            )
            if any(pattern in text for pattern in patterns):
                return self._experience_bucket(years)
        return None

    @staticmethod
    def _experience_bucket(years: int) -> str | None:
        if years < 0:
            return None
        if years == 0:
            return "Fresher"
        if years <= 2:
            return "1-2 Years"
        if years <= 4:
            return "3-5 Years"
        return "5+ Years"

    def _extract_worker_count(self, text: str) -> int | None:
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

        for phrase, count in self.TELUGU_WORKER_COUNTS.items():
            if phrase in text and any(term in text for term in ("worker", "వర్కర్", "staff", "సిబ్బంది", "మంది")):
                return count
        return None
