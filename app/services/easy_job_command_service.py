from typing import Optional

from app.repositories.job_lifecycle_repository import JobLifecycleRepository
from app.services.job_lifecycle_service import JobLifecycleService


class EasyJobCommandService:
    """Resolve simple text/voice phrases only when a matching job context exists."""

    ACCEPT_WORDS = {
        "1", "yes", "ok", "okay", "అవును", "సరే", "వస్తాను", "చేస్తాను",
        "పని చేస్తాను", "నేను వస్తాను", "నేను చేస్తాను",
    }
    REJECT_WORDS = {
        "2", "no", "వద్దు", "చేయను", "రాను", "నేను రాను", "నాకు వద్దు",
    }
    EMPLOYER_CONFIRM_WORDS = {
        "confirm", "confirm చేయండి", "ఇతనిని తీసుకోండి", "ఇతనే సరే",
        "ఈ worker సరే", "worker confirm", "అతనిని confirm చేయండి",
    }
    EMPLOYER_REJECT_WORDS = {
        "reject worker", "ఈ worker వద్దు", "ఇతను వద్దు", "అతను వద్దు",
    }
    CONTACT_PHRASES = (
        "phone number", "contact number", "mobile number", "give number",
        "ఫోన్ నంబర్", "కాంటాక్ట్ నంబర్", "నంబర్ ఇవ్వండి", "ఫోన్ ఇవ్వండి",
        "location share చేయలేను", "లోకేషన్ షేర్ చేయలేను",
        "location పంపలేను", "లోకేషన్ పంపలేను",
    )

    ONWAY_PHRASES = (
        "బయలుదేరాను", "బయలుదేరుతున్నాను", "వెళ్తున్నాను", "వస్తున్నాను",
        "on the way", "onway", "started travelling",
    )
    ARRIVED_PHRASES = (
        "చేరుకున్నాను", "వచ్చేశాను", "వచ్చాను", "చేరాను", "arrived", "reached",
    )
    START_PHRASES = (
        "పని మొదలుపెట్టాను", "పని మొదలైంది", "పని స్టార్ట్ చేశాను",
        "work started", "start work", "started work",
    )
    COMPLETE_PHRASES = (
        "పని అయిపోయింది", "పని పూర్తయింది", "పని పూర్తి చేశాను",
        "work completed", "work complete", "completed work", "finished work",
    )

    def __init__(
        self,
        repository: JobLifecycleRepository,
        lifecycle_service: JobLifecycleService,
    ) -> None:
        self.repository = repository
        self.lifecycle_service = lifecycle_service

    def process_text(self, sender_mobile: str, message: str) -> Optional[str]:
        clean = " ".join(str(message).strip().split())
        normalized = clean.lower()

        # Registration/onboarding owns short answers such as 1/2/yes/no. Fresh
        # Test deliberately preserves historical job rows, so an old pending job
        # must never steal a language/name/area answer from either text or voice.
        if not self._is_registered_user(sender_mobile):
            return None

        if not self._could_be_easy_job_command(normalized):
            return None

        pending_job_id = self._latest_pending_invitation(sender_mobile)
        if pending_job_id is not None:
            if normalized in self.ACCEPT_WORDS:
                return self.lifecycle_service.process_text(
                    sender_mobile,
                    f"ACCEPT {pending_job_id}",
                )
            if normalized in self.REJECT_WORDS:
                return self.lifecycle_service.process_text(
                    sender_mobile,
                    f"REJECT {pending_job_id}",
                )

        pending_worker = self._latest_pending_worker_for_employer(sender_mobile)
        if pending_worker is not None:
            job_id, worker_mobile = pending_worker
            if normalized in self.EMPLOYER_CONFIRM_WORDS:
                return self.lifecycle_service.process_text(
                    sender_mobile,
                    f"CONFIRM {job_id} {worker_mobile}",
                )
            if normalized in self.EMPLOYER_REJECT_WORDS:
                return self.lifecycle_service.process_text(
                    sender_mobile,
                    f"REJECTWORKER {job_id} {worker_mobile}",
                )

        if self._contains_any(normalized, self.CONTACT_PHRASES):
            fallback = getattr(self.lifecycle_service, "contact_fallback_for_active_job", None)
            if callable(fallback):
                result = fallback(sender_mobile)
                if result is not None:
                    return result

        active = self.repository.active_assignment_for_worker(sender_mobile)
        if not active:
            return None

        job_id = int(active["employer_job_id"])
        status = str(active["status"])

        if status == "CONFIRMED" and self._contains_any(normalized, self.ONWAY_PHRASES):
            return self.lifecycle_service.process_text(sender_mobile, f"ONWAY {job_id}")
        if status in {"CONFIRMED", "ON_THE_WAY"} and self._contains_any(
            normalized, self.ARRIVED_PHRASES
        ):
            return self.lifecycle_service.process_text(sender_mobile, f"ARRIVED {job_id}")
        if status == "ARRIVED" and self._contains_any(normalized, self.START_PHRASES):
            return self.lifecycle_service.process_text(sender_mobile, f"START {job_id}")
        if status == "WORK_STARTED" and self._contains_any(
            normalized, self.COMPLETE_PHRASES
        ):
            return self.lifecycle_service.process_text(sender_mobile, f"COMPLETE {job_id}")
        return None

    def _is_registered_user(self, sender_mobile: str) -> bool:
        finder = getattr(self.repository, "find_user", None)
        if not callable(finder):
            # Legacy repositories/tests predate registration-aware shortcut gating.
            # Preserve their historical behavior; production JobLifecycleRepository
            # exposes find_user(), so real onboarding still fails closed.
            return True
        try:
            row = finder(sender_mobile)
            return bool(row and int(row.get("registration_complete") or 0) == 1)
        except Exception:
            # In production, an unreadable registration state must never let a
            # historical job shortcut bypass onboarding.
            return False

    def _latest_pending_invitation(self, worker_mobile: str) -> Optional[int]:
        row = self.repository.database.fetchone(
            """
            SELECT n.employer_job_id
            FROM match_notifications n
            JOIN employer_jobs j ON j.id = n.employer_job_id
            LEFT JOIN job_assignments a
              ON a.employer_job_id = n.employer_job_id
             AND a.worker_mobile = n.worker_mobile
            WHERE n.worker_mobile = ?
              AND n.created_at >= datetime('now', '-24 hours')
              AND j.status IN ('OPEN', 'FILLED')
              AND (a.id IS NULL OR a.status IN ('REJECTED', 'CANCELLED'))
            ORDER BY n.created_at DESC, n.id DESC
            LIMIT 1
            """,
            (worker_mobile,),
        )
        return int(row["employer_job_id"]) if row else None

    def _latest_pending_worker_for_employer(self, employer_mobile: str) -> Optional[tuple[int, str]]:
        row = self.repository.database.fetchone(
            """
            SELECT a.employer_job_id, a.worker_mobile
            FROM job_assignments a
            JOIN employer_jobs j ON j.id = a.employer_job_id
            WHERE j.employer_mobile = ?
              AND a.status = 'PENDING_CONFIRMATION'
              AND j.status IN ('OPEN', 'FILLED')
            ORDER BY a.updated_at DESC, a.id DESC
            LIMIT 1
            """,
            (employer_mobile,),
        )
        if not row:
            return None
        return int(row["employer_job_id"]), str(row["worker_mobile"])

    def _could_be_easy_job_command(self, normalized: str) -> bool:
        if normalized in self.ACCEPT_WORDS or normalized in self.REJECT_WORDS:
            return True
        if normalized in self.EMPLOYER_CONFIRM_WORDS or normalized in self.EMPLOYER_REJECT_WORDS:
            return True
        if self._contains_any(normalized, self.CONTACT_PHRASES):
            return True
        lifecycle_phrases = (
            self.ONWAY_PHRASES
            + self.ARRIVED_PHRASES
            + self.START_PHRASES
            + self.COMPLETE_PHRASES
        )
        return self._contains_any(normalized, lifecycle_phrases)

    @staticmethod
    def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
        return any(phrase in text for phrase in phrases)
