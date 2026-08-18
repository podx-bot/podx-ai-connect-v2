"""Universal category and side classifier for PODX app-flow orchestration.

This module is intentionally deterministic. It does not own vertical business
logic; it produces a stable routing plan so unrelated runtimes cannot compete
for the same user message. AI/LLM fallback may sit behind this contract later,
but stateful app routing should never depend on it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryFlowDecision:
    category: str
    side: str
    action: str
    confidence: float
    source: str = "rules"


class UniversalCategoryFlowBrain:
    CATEGORIES = {
        "JOBS", "COMMERCE", "SERVICES", "FREELANCE", "MOBILITY", "FOOD",
        "DELIVERY", "HEALTHCARE", "PROPERTY", "TRAVEL", "B2B_RFQ",
        "APPOINTMENT", "EVENT", "PROFILE", "SUPPORT", "GENERAL",
    }

    def classify(self, message: str) -> CategoryFlowDecision:
        text = " ".join(str(message or "").casefold().split())
        if not text:
            return CategoryFlowDecision("GENERAL", "UNKNOWN", "UNKNOWN", 0.0, "empty")

        if any(term in text for term in ("my profile", "నా ప్రొఫైల్", "profile చూప")):
            return CategoryFlowDecision("PROFILE", "SELF", "VIEW", 1.0)
        if any(term in text for term in ("help", "సహాయం", "support", "admin", "complaint", "ఫిర్యాదు")):
            return CategoryFlowDecision("SUPPORT", "SEEKER", "RESOLVE", 0.98)

        appointment = (
            "appointment", "doctor booking", "clinic booking", "hospital appointment",
            "salon booking", "అపాయింట్మెంట్", "డాక్టర్ బుకింగ్", "సెలూన్ బుకింగ్",
        )
        if any(term in text for term in appointment):
            return CategoryFlowDecision("APPOINTMENT", "SEEKER", "BOOK", 0.99)

        mobility_offer = (
            "seats ఉన్నాయి", "seat ఉంది", "empty seats", "offer ride", "post ride",
            "carలో", "bikeలో", "బైక్ లో", "కారులో", "ride ఇస్తాను", "lift ఇస్తాను",
        )
        mobility_seek = (
            "cab కావాలి", "taxi కావాలి", "ride కావాలి", "car కావాలి", "bike taxi",
            "airportకి వెళ్లాలి", "airport కు వెళ్లాలి", "pickup", "drop", "uber", "ola", "rapido",
        )
        if any(term in text for term in mobility_offer):
            return CategoryFlowDecision("MOBILITY", "PROVIDER", "OFFER", 0.98)
        if any(term in text for term in mobility_seek):
            return CategoryFlowDecision("MOBILITY", "SEEKER", "BOOK", 0.98)

        job_seek = (
            "job కావాలి", "జాబ్ కావాలి", "పని కావాలి", "ఉద్యోగం కావాలి", "need a job",
            "looking for job", "looking for work", "work కావాలి", "नौकरी चाहिए",
        )
        job_hire = (
            "workers కావాలి", "worker కావాలి", "staff కావాలి", "వర్కర్స్ కావాలి",
            "need workers", "need staff", "hire workers", "workers required",
        )
        counted_hire_patterns = (
            r"\bneed\s+\d{1,3}\s+(?:workers?|staff)\b",
            r"\bhire\s+\d{1,3}\s+(?:workers?|staff)\b",
            r"\b\d{1,3}\s+(?:workers?|staff)\s+(?:needed|required)\b",
            r"\b\d{1,3}\s+(?:workers?|staff)\s+కావాలి",
            r"\b(?:workers?|staff)\s+\d{1,3}\s+కావాలి",
        )
        if any(term in text for term in job_seek):
            return CategoryFlowDecision("JOBS", "SEEKER", "FIND", 0.99)
        if any(term in text for term in job_hire) or any(
            re.search(pattern, text) for pattern in counted_hire_patterns
        ):
            return CategoryFlowDecision("JOBS", "PROVIDER", "HIRE", 0.99)

        freelance_terms = (
            "freelancer", "freelance", "logo design", "website design", "graphic design",
            "video edit", "content writer", "developer project", "upwork", "fiverr",
        )
        if any(term in text for term in freelance_terms):
            side = "PROVIDER" if any(x in text for x in ("i do", "నేను చేస్తాను", "provide", "offer")) else "SEEKER"
            action = "OFFER" if side == "PROVIDER" else "HIRE"
            return CategoryFlowDecision("FREELANCE", side, action, 0.95)

        service_provider = (
            "service ఇస్తాను", "service చేస్తాను", "సర్వీస్ ఇస్తాను", "సేవ ఇస్తాను",
            "i provide service", "service provider", "నేను electrician", "నేను plumber",
            "నేను carpenter", "నేను tailor", "నేను mechanic",
        )
        service_seek = (
            "electrician", "plumber", "ac repair", "ac service", "house cleaning", "cleaning service",
            "tailor", "alteration", "carpenter", "mechanic", "service కావాలి", "సర్వీస్ కావాలి",
            "ఎలక్ట్రిషియన్", "ప్లంబర్", "ఏసీ రిపేర్", "టైలర్", "కార్పెంటర్", "మెకానిక్",
        )
        if any(term in text for term in service_provider):
            return CategoryFlowDecision("SERVICES", "PROVIDER", "OFFER", 0.99)
        if any(term in text for term in service_seek):
            return CategoryFlowDecision("SERVICES", "SEEKER", "BOOK", 0.96)

        healthcare = (
            "doctor", "డాక్టర్", "hospital", "హాస్పిటల్", "clinic", "క్లినిక్",
            "medicine", "మెడిసిన్", "pharmacy", "ఫార్మసీ", "lab test", "diagnostic",
        )
        if any(term in text for term in healthcare):
            return CategoryFlowDecision("HEALTHCARE", "SEEKER", "FIND", 0.92)

        property_terms = (
            "house rent", "rent house", "flat rent", "property", "plot", "apartment",
            "ఇల్లు అద్దె", "ఫ్లాట్", "ప్లాట్", "rent కావాలి", "sell house", "house అమ్మాలి",
        )
        if any(term in text for term in property_terms):
            side = "PROVIDER" if any(x in text for x in ("sell", "అమ్మాలి", "for rent", "rentకి ఇస్తాను")) else "SEEKER"
            return CategoryFlowDecision("PROPERTY", side, "LIST" if side == "PROVIDER" else "FIND", 0.94)

        travel_terms = (
            "hotel room", "flight", "train ticket", "bus ticket", "trip package", "travel booking",
            "హోటల్ రూమ్", "ఫ్లైట్", "ట్రైన్ టికెట్", "బస్ టికెట్", "ట్రిప్",
        )
        if any(term in text for term in travel_terms):
            return CategoryFlowDecision("TRAVEL", "SEEKER", "BOOK", 0.94)

        food_terms = (
            "food order", "meal", "biryani", "restaurant food", "tiffin", "lunch", "dinner",
            "ఫుడ్ ఆర్డర్", "బిర్యానీ", "టిఫిన్", "భోజనం",
        )
        if any(term in text for term in food_terms):
            return CategoryFlowDecision("FOOD", "SEEKER", "ORDER", 0.92)

        delivery_terms = (
            "parcel", "courier", "delivery boy", "pickup parcel", "send parcel", "local delivery",
            "పార్సల్", "కూరియర్", "డెలివరీ చేయాలి", "పికప్ చేయాలి",
        )
        if any(term in text for term in delivery_terms):
            return CategoryFlowDecision("DELIVERY", "SEEKER", "BOOK", 0.94)

        b2b_terms = (
            "quotation", "quote కావాలి", "rfq", "bulk order", "wholesale", "tender",
            "కోటేషన్", "బల్క్", "హోల్‌సేల్", "supplier quote",
        )
        if any(term in text for term in b2b_terms):
            return CategoryFlowDecision("B2B_RFQ", "SEEKER", "REQUEST_QUOTES", 0.97)

        event_terms = (
            "event", "function", "wedding", "birthday function", "catering function",
            "ఫంక్షన్", "వెడ్డింగ్", "బర్త్‌డే ఫంక్షన్",
        )
        if any(term in text for term in event_terms):
            return CategoryFlowDecision("EVENT", "SEEKER", "PLAN", 0.92)

        sell_terms = (
            "అమ్ముతాను", "అమ్మాలి", "sell product", "i sell", "we sell", "seller",
            "stock ఉంది", "available for sale", "బెచ్తా", "बेचना है",
        )
        buy_terms = (
            "కావాలి", "buy", "కొనాలి", "price", "ధర", "rate", "రేట్", "stock ఉందా",
            "available ఉందా", "order చేయాలి", "purchase", "need product",
        )
        if any(term in text for term in sell_terms):
            return CategoryFlowDecision("COMMERCE", "PROVIDER", "SELL", 0.93)
        if any(term in text for term in buy_terms):
            return CategoryFlowDecision("COMMERCE", "SEEKER", "BUY", 0.82)

        return CategoryFlowDecision("GENERAL", "UNKNOWN", "UNKNOWN", 0.2, "fallback")
