"""Unified user-facing profile summary for Universal Registration/Profile V2."""
from __future__ import annotations


class UniversalProfileSummaryService:
    PROFILE_COMMANDS = {
        "my profile", "profile", "show profile", "నా ప్రొఫైల్", "ప్రొఫైల్ చూపించు",
        "నా profile", "profile చూపించు", "मेरा प्रोफाइल", "प्रोफाइल दिखाओ",
    }

    ROLE_LABELS = {
        "BUYER": "Buyer",
        "SELLER": "Seller",
        "SERVICE_CUSTOMER": "Service Customer",
        "SERVICE_PROVIDER": "Service Provider",
        "WORKER": "Worker / Job Seeker",
        "EMPLOYER": "Employer",
    }

    def __init__(self, delegate, user_repository, marketplace_repository=None) -> None:
        self.delegate = delegate
        self.users = user_repository
        self.marketplace = marketplace_repository

    def process(self, sender_mobile: str, message: str) -> str:
        clean = " ".join(str(message or "").strip().split())
        if clean.casefold() not in {value.casefold() for value in self.PROFILE_COMMANDS}:
            return self._call_delegate(sender_mobile, clean)
        return self._summary(sender_mobile)

    def _summary(self, sender_mobile: str) -> str:
        try:
            user = self.users.find_by_whatsapp_mobile(sender_mobile)
        except Exception:
            user = None
        if not user or int(user.get("registration_complete") or 0) != 1:
            return "మీ Universal Profile ఇంకా complete కాలేదు. Hi పంపి registration పూర్తి చేయండి."

        capabilities = [str(value).upper() for value in (user.get("capabilities") or [])]
        role_text = ", ".join(self.ROLE_LABELS.get(value, value) for value in capabilities) or "ఇంకా ఏ role activate కాలేదు"

        lines = [
            "👤 మీ PODX Universal Profile",
            "",
            f"పేరు: {user.get('name') or '-'}",
            f"WhatsApp: {user.get('whatsapp_mobile') or sender_mobile}",
            f"భాష: {user.get('language') or '-'}",
            f"ప్రాంతం: {user.get('area') or user.get('location_name') or '-'}",
            f"Roles: {role_text}",
        ]

        if "WORKER" in capabilities:
            lines.extend([
                "",
                "👷 Worker Profile",
                f"పని: {user.get('job_category') or 'Pending'}",
                f"Experience: {user.get('experience') or 'Pending'}",
                f"Availability: {user.get('availability') or 'Pending'}",
                f"Location: {'Saved' if user.get('latitude') is not None and user.get('longitude') is not None else 'Pending'}",
            ])

        seller_rows = self._marketplace_rows("list_seller_listings_for_user", sender_mobile)
        if seller_rows:
            names = self._unique([row.get("product_name") for row in seller_rows])
            lines.extend(["", f"🛍️ Active Seller Listings: {len(seller_rows)}", "Products: " + ", ".join(names[:5])])

        provider_rows = self._marketplace_rows("list_service_provider_profiles_for_user", sender_mobile)
        if provider_rows:
            names = self._unique([row.get("service_name") for row in provider_rows])
            lines.extend(["", f"🛠️ Service Profiles: {len(provider_rows)}", "Services: " + ", ".join(names[:5])])

        lines.extend(["", "మీకు కావాల్సింది మీ మాటల్లో చెప్పండి; అవసరమైన role PODX ఆటోమేటిక్‌గా ఉపయోగిస్తుంది."])
        return "\n".join(lines)

    def _marketplace_rows(self, method_name: str, sender_mobile: str) -> list[dict]:
        if self.marketplace is None:
            return []
        try:
            method = getattr(self.marketplace, method_name, None)
            return list(method(sender_mobile) or []) if callable(method) else []
        except Exception:
            return []

    @staticmethod
    def _unique(values) -> list[str]:
        seen = set()
        result = []
        for value in values:
            text = str(value or "").strip()
            key = text.casefold()
            if not text or key in seen:
                continue
            seen.add(key)
            result.append(text)
        return result

    def _call_delegate(self, sender_mobile: str, message: str) -> str:
        process = getattr(self.delegate, "process", None)
        if callable(process):
            return process(sender_mobile, message)
        if callable(self.delegate):
            return self.delegate(sender_mobile, message)
        return ""
