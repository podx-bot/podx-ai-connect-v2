"""Privacy-safe job lifecycle with low-literacy contact fallback."""
from __future__ import annotations

import re
from typing import Optional

from app.services.job_lifecycle_service import JobLifecycleService


class JobConsentLifecycleService(JobLifecycleService):
    """Keep phone numbers private until worker interest and employer confirmation agree."""

    CONTACT_PHRASES = (
        "contact", "phone", "number", "mobile", "call",
        "ఫోన్", "నంబర్", "కాంటాక్ట్", "కాల్చేయ", "కాల్ చేయ",
        "location share చేయలేను", "లోకేషన్ షేర్ చేయలేను",
        "location పంపలేను", "లోకేషన్ పంపలేను",
    )

    def process_text(self, sender_mobile: str, message: str) -> Optional[str]:
        clean = " ".join(str(message or "").strip().split())
        explicit = re.fullmatch(r"CONTACT(?:\s+#?(\d+))?", clean.upper())
        if explicit:
            job_id = int(explicit.group(1)) if explicit.group(1) else None
            return self._contact_fallback(sender_mobile, job_id)
        return super().process_text(sender_mobile, clean)

    def _accept_job(self, worker_mobile: str, job_id: int) -> str:
        result = self.repository.accept_job(job_id, worker_mobile)
        if not result.get("ok"):
            reason = result.get("reason")
            if reason == "JOB_NOT_FOUND":
                return f"❌ Job #{job_id} దొరకలేదు."
            if reason == "SELF_ACCEPT":
                return "❌ మీ సొంత Jobను మీరు accept చేయలేరు."
            return f"⚠️ Job #{job_id} ప్రస్తుతం accept చేయడానికి available లేదు."

        assignment = result.get("assignment") or {}
        if result.get("reason") == "ALREADY_ACCEPTED":
            return (
                f"ℹ️ Job #{job_id} మీరు ఇప్పటికే accept చేశారు.\n"
                f"Status: {self.STATUS_LABELS.get(assignment.get('status'), assignment.get('status'))}"
            )

        job = result["job"]
        worker = result.get("worker") or self.repository.find_user(worker_mobile) or {}
        worker_name = worker.get("name") or "Worker"
        distance = self._worker_job_distance(worker, job)
        distance_text = f"{distance:.2f} km" if distance is not None else "-"

        employer_message = (
            f"🙋 Worker interested — Job #{job_id}\n\n"
            f"Worker: {worker_name}\n"
            f"Distance: {distance_text}\n"
            "🔒 Contact is hidden until you confirm this worker.\n\n"
            f"Confirm: CONFIRM {job_id} {worker_mobile}\n"
            f"Reject: REJECTWORKER {job_id} {worker_mobile}"
        )
        self._send(str(job["employer_mobile"]), employer_message)
        return (
            f"✅ Job #{job_id} interest employerకి పంపాం.\n"
            "Employer confirm చేసిన తర్వాత ఇద్దరికీ contact details వస్తాయి.\n"
            "Location share చేయడం కష్టమైతే తర్వాత ‘ఫోన్ నంబర్ ఇవ్వండి’ అని చెప్పండి."
        )

    def contact_fallback_for_active_job(self, sender_mobile: str) -> Optional[str]:
        assignment = self.repository.active_assignment_for_worker(sender_mobile)
        if not assignment:
            return None
        return self._contact_fallback(sender_mobile, int(assignment["employer_job_id"]))

    def _contact_fallback(self, worker_mobile: str, job_id: int | None) -> str:
        assignment = None
        if job_id is not None:
            assignment = self.repository.find_assignment(job_id, worker_mobile)
            if assignment:
                job = self.repository.find_job(job_id) or {}
                assignment = {**assignment, **{
                    "employer_mobile": job.get("employer_mobile"),
                    "employer_contact": job.get("employer_contact"),
                    "service": job.get("service"),
                }}
        else:
            assignment = self.repository.active_assignment_for_worker(worker_mobile)

        if not assignment:
            return "❌ Confirmed job assignment దొరకలేదు."
        status = str(assignment.get("status") or "")
        if status not in {"CONFIRMED", "ON_THE_WAY", "ARRIVED", "WORK_STARTED"}:
            return "🔒 Employer confirmation తర్వాత మాత్రమే contact details share చేస్తాం."

        job_id = int(assignment["employer_job_id"])
        job = self.repository.find_job(job_id) or {}
        worker = self.repository.find_user(worker_mobile) or {}
        employer_mobile = str(job.get("employer_mobile") or assignment.get("employer_mobile") or "")
        employer_contact = str(job.get("employer_contact") or employer_mobile)
        worker_contact = str(worker.get("entered_mobile") or worker_mobile)
        worker_name = str(worker.get("name") or "Worker")

        if employer_mobile:
            self._send(
                employer_mobile,
                f"☎️ Job #{job_id} contact fallback\nWorker: {worker_name}\nContact: {worker_contact}",
            )
        return (
            f"☎️ Job #{job_id} employer contact: {employer_contact}\n"
            "Location share చేయలేకపోయినా ఈ number ద్వారా directగా coordinate చేసుకోవచ్చు."
        )
