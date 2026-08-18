"""Universal user correction/edit intelligence."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CorrectionIntent:
    target: str
    value: str
    raw: str


class UniversalCorrectionService:
    MARKERS = (
        "sorry", "actually", "instead", "change", "correct", "correction",
        "no ", "not ", "wrong", "mistake",
        "క్షమించండి", "సారీ", "కాదు", "మార్చు", "మార్చండి", "తప్పు", "సరిచేయ",
        "गलत", "नहीं", "बदलो", "सही",
    )
    ROLE_MAP = {
        "1": "BUYER", "2": "SELLER", "3": "SERVICE_CUSTOMER",
        "4": "SERVICE_PROVIDER", "5": "WORKER", "6": "EMPLOYER",
    }
    ROLE_LABELS = {
        "BUYER": "Buy products", "SELLER": "Sell products",
        "SERVICE_CUSTOMER": "Need services", "SERVICE_PROVIDER": "Provide services",
        "WORKER": "Find work", "EMPLOYER": "Hire workers",
    }
    ALL_ROLES = tuple(ROLE_LABELS)
    LANGUAGE_MAP = {
        "telugu": "Telugu", "తెలుగు": "Telugu", "english": "English",
        "hindi": "Hindi", "हिंदी": "Hindi", "tamil": "Tamil", "தமிழ்": "Tamil",
        "kannada": "Kannada", "ಕನ್ನಡ": "Kannada", "malayalam": "Malayalam", "മലയാളം": "Malayalam",
        "marathi": "Marathi", "मराठी": "Marathi", "bengali": "Bengali", "bangla": "Bengali", "বাংলা": "Bengali",
        "gujarati": "Gujarati", "ગુજરાતી": "Gujarati", "punjabi": "Punjabi", "ਪੰਜਾਬੀ": "Punjabi",
        "odia": "Odia", "oriya": "Odia", "ଓଡ଼ିଆ": "Odia", "urdu": "Urdu", "اردو": "Urdu",
        "assamese": "Assamese", "অসমীয়া": "Assamese",
    }

    def __init__(self, delegate, user_repository=None, session_registry=None) -> None:
        self.delegate = delegate
        self.users = user_repository
        self.sessions = session_registry
        self._ensure_schema()

    def process(self, sender_mobile: str, message: str) -> str:
        sender = str(sender_mobile)
        clean = str(message or "").strip()
        intent = self.detect(clean, sender)
        if intent is not None:
            applied = self._apply(sender, intent)
            if applied is not None:
                return applied
        return self.delegate.process(sender_mobile=sender, message=clean)

    def detect(self, message: str, sender_mobile: Optional[str] = None) -> Optional[CorrectionIntent]:
        clean = " ".join(str(message or "").strip().split())
        low = clean.casefold()
        if not clean or not any(marker in low for marker in self.MARKERS):
            return None
        explicit = self._explicit_target(clean, low)
        if explicit is not None:
            return explicit
        if self._recent_target(sender_mobile) == "roles":
            value = self._role_value(clean)
            if value:
                return CorrectionIntent("roles", value, clean)
        return None

    def _explicit_target(self, clean: str, low: str) -> Optional[CorrectionIntent]:
        role_value = self._role_value(clean)
        if role_value and any(w in low for w in ("role", "roles", "buyer", "seller", "worker", "employer", "service", "all", "అన్నీ", "అన్ని")):
            return CorrectionIntent("roles", role_value, clean)
        if any(w in low for w in ("language", "భాష", "भाषा")):
            value = self._extract_language(low)
            if value:
                return CorrectionIntent("language", value, clean)
        if any(w in low for w in ("location", "area", "town", "city", "ప్రాంతం", "పట్టణం", "లొకేషన్", "शहर")):
            value = self._after_change_words(clean)
            if value:
                return CorrectionIntent("area", value, clean)
        if any(w in low for w in ("name", "పేరు", "नाम")):
            value = self._after_change_words(clean)
            if value:
                return CorrectionIntent("name", value, clean)
        for target, words in (
            ("quantity", ("quantity", "qty", "kg", "pieces", "క్వాంటిటీ")),
            ("price", ("price", "rate", "₹", "ధర", "రేట్")),
            ("date", ("date", "tomorrow", "today", "తేదీ", "రేపు", "ఈరోజు")),
            ("delivery", ("delivery", "pickup", "డెలివరీ", "పికప్")),
        ):
            if any(w in low for w in words):
                return CorrectionIntent(target, clean, clean)
        return None

    def _recent_target(self, sender_mobile: Optional[str]) -> Optional[str]:
        if not sender_mobile or self.sessions is None:
            return None
        try:
            data = getattr(self.sessions.get(str(sender_mobile)), "data", {}) or {}
            return "roles" if data.get("registration_capabilities") is not None else None
        except Exception:
            return None

    def _role_value(self, clean: str) -> Optional[str]:
        low = clean.casefold()
        # Match ALL only as a standalone token. This prevents words such as
        # "actually" from being misread as the All-roles command.
        if re.search(r"(?:^|\W)(?:7|all)(?:\W|$)", low) or any(x in low for x in ("అన్నీ", "అన్ని")):
            return "ALL"
        found: list[str] = []
        for number, role in self.ROLE_MAP.items():
            if re.search(rf"(?:^|\D){number}(?:\D|$)", low):
                found.append(role)
        word_map = {
            "buyer": "BUYER", "కొనాలి": "BUYER", "seller": "SELLER", "అమ్మాలి": "SELLER",
            "service customer": "SERVICE_CUSTOMER", "service కావాలి": "SERVICE_CUSTOMER",
            "service provider": "SERVICE_PROVIDER", "service ఇవ్వాలి": "SERVICE_PROVIDER",
            "worker": "WORKER", "పని కావాలి": "WORKER", "employer": "EMPLOYER", "workers కావాలి": "EMPLOYER",
        }
        for phrase, role in word_map.items():
            if phrase in low and role not in found:
                found.append(role)
        return ",".join(found) if found else None

    def _extract_language(self, low: str) -> Optional[str]:
        for key, value in self.LANGUAGE_MAP.items():
            if key in low:
                return value
        cleaned = re.sub(r"(?i)\b(?:sorry|actually|change|correct|language|to|is|no|not)\b", " ", low)
        cleaned = re.sub(r"(?:సారీ|క్షమించండి|కాదు|మార్చు|మార్చండి|భాష|गलत|नहीं|बदलो|भाषा)", " ", cleaned)
        candidate = " ".join(cleaned.split()).strip(" ,:-")
        return candidate.title() if candidate and len(candidate) <= 40 else None

    @staticmethod
    def _after_change_words(clean: str) -> str:
        text = re.sub(r"(?i)\b(?:sorry|actually|instead|change|correct|correction|name|area|town|city|location|language|to|is|not|no)\b", " ", clean)
        text = re.sub(r"(?:సారీ|క్షమించండి|కాదు|మార్చు|మార్చండి|తప్పు|పేరు|ప్రాంతం|పట్టణం|లొకేషన్|భాష)", " ", text)
        return " ".join(text.split()).strip(" ,:-")

    def _apply(self, sender: str, intent: CorrectionIntent) -> Optional[str]:
        if self.users is None:
            return None
        db = getattr(self.users, "database", None)
        user = self.users.find_by_whatsapp_mobile(sender)
        if not user or int(user.get("registration_complete") or 0) != 1:
            return None
        if intent.target == "roles":
            old = list(user.get("capabilities") or [])
            new = list(self.ALL_ROLES) if intent.value == "ALL" else [x for x in intent.value.split(",") if x]
            if not new:
                return None
            if db is not None:
                db.execute("DELETE FROM user_capabilities WHERE whatsapp_mobile=?", (sender,))
            self.users.add_capabilities(sender, new, source="user_correction")
            self._audit(sender, "roles", old, new, intent.raw)
            self._remember_roles(sender, new)
            labels = ", ".join(self.ROLE_LABELS[x] for x in new)
            return f"✅ సరే. మీ PODX roles మార్చాను: {labels}. ఇక మీకు ఏం కావాలో సహజంగా చెప్పండి."
        if intent.target in {"name", "language", "area"} and db is not None:
            old = user.get(intent.target)
            db.execute(f"UPDATE users SET {intent.target}=?, updated_at=CURRENT_TIMESTAMP WHERE whatsapp_mobile=?", (intent.value, sender))
            self._audit(sender, intent.target, old, intent.value, intent.raw)
            label = {"name": "పేరు", "language": "భాష", "area": "ప్రాంతం"}[intent.target]
            return f"✅ {label} {old or '-'} → {intent.value}గా మార్చాను."
        return None

    def _remember_roles(self, sender: str, roles: list[str]) -> None:
        if self.sessions is None:
            return
        try:
            data = getattr(self.sessions.get(sender), "data", None)
            if isinstance(data, dict):
                data["registration_capabilities"] = roles
                data["last_corrected_field"] = "roles"
        except Exception:
            pass

    def _ensure_schema(self) -> None:
        db = getattr(self.users, "database", None) if self.users is not None else None
        if db is not None:
            db.execute("CREATE TABLE IF NOT EXISTS user_correction_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, whatsapp_mobile TEXT NOT NULL, field_name TEXT NOT NULL, old_value TEXT, new_value TEXT, raw_message TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")

    def _audit(self, sender: str, field: str, old, new, raw: str) -> None:
        db = getattr(self.users, "database", None) if self.users is not None else None
        if db is not None:
            db.execute("INSERT INTO user_correction_audit(whatsapp_mobile,field_name,old_value,new_value,raw_message) VALUES(?,?,?,?,?)", (sender, field, str(old), str(new), raw))
