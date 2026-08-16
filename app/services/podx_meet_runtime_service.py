"""WhatsApp runtime for local PODX Meet community events."""
from __future__ import annotations

import re
from typing import Optional


class PodxMeetRuntimeService:
    def __init__(self, repository, user_repository=None) -> None:
        self.repository = repository
        self.users = user_repository

    def process(self, sender_user_id: str, message: str) -> Optional[str]:
        clean = " ".join(str(message or "").strip().split())
        if not clean:
            return None
        lowered = clean.casefold()
        if not (lowered.startswith("meet ") or lowered == "meet" or lowered.startswith("podx meet")):
            return None
        if not self._registered(sender_user_id):
            return None

        normalized = re.sub(r"^podx\s+", "", clean, flags=re.IGNORECASE)
        if re.fullmatch(r"meet\s+help", normalized, flags=re.IGNORECASE) or normalized.casefold() == "meet":
            return self._help()
        match = re.fullmatch(r"meet\s+create\s+(.+)", normalized, flags=re.IGNORECASE)
        if match:
            return self._create(sender_user_id, match.group(1))
        match = re.fullmatch(r"meet\s+find(?:\s+(.+))?", normalized, flags=re.IGNORECASE)
        if match:
            return self._find(sender_user_id, match.group(1))
        match = re.fullmatch(r"meet\s+join\s+#?(\d+)", normalized, flags=re.IGNORECASE)
        if match:
            return self._join(sender_user_id, int(match.group(1)))
        match = re.fullmatch(r"meet\s+leave\s+#?(\d+)", normalized, flags=re.IGNORECASE)
        if match:
            return self._leave(sender_user_id, int(match.group(1)))
        match = re.fullmatch(r"meet\s+status\s+#?(\d+)", normalized, flags=re.IGNORECASE)
        if match:
            return self._status(sender_user_id, int(match.group(1)))
        match = re.fullmatch(r"meet\s+cancel\s+#?(\d+)", normalized, flags=re.IGNORECASE)
        if match:
            return self._cancel(sender_user_id, int(match.group(1)))
        return self._help()

    def _create(self, sender_user_id: str, body: str) -> str:
        parts = [" ".join(part.split()) for part in str(body).split("|")]
        if len(parts) < 3 or not all(parts[:3]):
            return "Format: MEET CREATE <title> | <date/time> | <area> | <optional details>"
        title, scheduled_text, area = parts[:3]
        details = parts[3] if len(parts) > 3 else ""
        meet_id = self.repository.create(sender_user_id, title, scheduled_text, area, details)
        return (
            f"✅ PODX Meet #{meet_id} create అయింది.\n"
            f"{title} — {scheduled_text} — {area}\n"
            f"People join చేయడానికి: MEET JOIN {meet_id}"
        )

    def _find(self, sender_user_id: str, area: str | None) -> str:
        effective_area = " ".join(str(area or "").split()) or self._user_area(sender_user_id)
        rows = self.repository.list_open(effective_area or None, limit=8)
        if not rows and effective_area:
            rows = self.repository.list_open(None, limit=8)
        if not rows:
            return "ప్రస్తుతం open PODX Meets లేవు."
        heading = f"📍 PODX Meets — {effective_area}" if effective_area else "📍 Open PODX Meets"
        lines = [heading]
        for row in rows:
            count = self.repository.attendee_count(int(row["id"]))
            lines.append(
                f"#{row['id']} {row['title']} — {row['scheduled_text']} — {row['area']} — {count} joined"
            )
        lines.append("Join: MEET JOIN <id>")
        return "\n".join(lines)

    def _join(self, sender_user_id: str, meet_id: int) -> str:
        meet = self.repository.get(meet_id)
        if not meet or str(meet.get("status")) != "OPEN":
            return f"PODX Meet #{meet_id} openగా లేదు."
        if self.repository.is_joined(meet_id, sender_user_id):
            return f"✅ మీరు PODX Meet #{meet_id}కి ఇప్పటికే joined అయ్యారు."
        if not self.repository.join(meet_id, sender_user_id):
            return f"PODX Meet #{meet_id} join చేయలేకపోయాను."
        count = self.repository.attendee_count(meet_id)
        return (
            f"✅ PODX Meet #{meet_id}కి joined అయ్యారు.\n"
            f"{meet['title']} — {meet['scheduled_text']} — {meet['area']}\n"
            f"Current attendees: {count}"
        )

    def _leave(self, sender_user_id: str, meet_id: int) -> str:
        if self.repository.leave(meet_id, sender_user_id):
            return f"✅ PODX Meet #{meet_id} నుంచి leave అయ్యారు."
        return f"మీరు PODX Meet #{meet_id}కి currently joinedగా లేరు."

    def _status(self, sender_user_id: str, meet_id: int) -> str:
        meet = self.repository.get(meet_id)
        if not meet:
            return f"PODX Meet #{meet_id} దొరకలేదు."
        count = self.repository.attendee_count(meet_id)
        joined = self.repository.is_joined(meet_id, sender_user_id)
        return (
            f"📍 PODX Meet #{meet_id}\n"
            f"{meet['title']}\n"
            f"When: {meet['scheduled_text']}\n"
            f"Area: {meet['area']}\n"
            f"Status: {meet['status']}\n"
            f"Attendees: {count}\n"
            f"You: {'JOINED' if joined else 'NOT JOINED'}"
        )

    def _cancel(self, sender_user_id: str, meet_id: int) -> str:
        meet = self.repository.get(meet_id)
        if not meet:
            return f"PODX Meet #{meet_id} దొరకలేదు."
        if str(meet.get("host_user_id")) != str(sender_user_id):
            return "ఈ PODX Meetని host మాత్రమే cancel చేయగలరు."
        if self.repository.cancel(meet_id, sender_user_id):
            return f"✅ PODX Meet #{meet_id} cancelled."
        return f"PODX Meet #{meet_id} ఇప్పటికే {meet.get('status')} stateలో ఉంది."

    def _registered(self, user_id: str) -> bool:
        if self.users is None:
            return True
        user = self.users.find_by_whatsapp_mobile(str(user_id)) or {}
        return int(user.get("registration_complete") or 0) == 1

    def _user_area(self, user_id: str) -> str:
        if self.users is None:
            return ""
        user = self.users.find_by_whatsapp_mobile(str(user_id)) or {}
        return str(user.get("area") or user.get("location_name") or "").strip()

    @staticmethod
    def _help() -> str:
        return (
            "PODX Meet commands:\n"
            "MEET CREATE <title> | <date/time> | <area> | <details>\n"
            "MEET FIND [area]\n"
            "MEET JOIN <id>\n"
            "MEET LEAVE <id>\n"
            "MEET STATUS <id>\n"
            "MEET CANCEL <id>"
        )
