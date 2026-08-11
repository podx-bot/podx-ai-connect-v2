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

    @staticmethod
    def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
        return any(phrase in text for phrase in phrases)
