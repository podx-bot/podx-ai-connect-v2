import re
from math import asin, cos, radians, sin, sqrt
from typing import Optional

from app.repositories.job_lifecycle_repository import JobLifecycleRepository
from app.whatsapp.whatsapp_service import WhatsAppService


class JobLifecycleService:
    STATUS_LABELS = {
        "PENDING_CONFIRMATION": "Employer confirmation కోసం waiting",
        "CONFIRMED": "Confirmed",
        "ON_THE_WAY": "On the way",
        "ARRIVED": "Arrived",
        "WORK_STARTED": "Work started",
        "COMPLETED": "Completed",
        "REJECTED": "Rejected",
    }

    def __init__(
        self,
        repository: JobLifecycleRepository,
        whatsapp_service: WhatsAppService,
        arrival_radius_km: float = 0.20
    ) -> None:
        self.repository = repository
        self.whatsapp_service = whatsapp_service
        self.arrival_radius_km = float(arrival_radius_km)

    def process_text(self, sender_mobile: str, message: str) -> Optional[str]:
        clean = str(message).strip()
        normalized = clean.upper()

        match = re.fullmatch(r"ACCEPT\s+#?(\d+)", normalized)
        if match:
            return self._accept_job(sender_mobile, int(match.group(1)))

        match = re.fullmatch(r"REJECT\s+#?(\d+)", normalized)
        if match:
            return self._reject_invitation(sender_mobile, int(match.group(1)))

        match = re.fullmatch(r"CONFIRM\s+#?(\d+)\s+(\+?\d{10,15})", normalized)
        if match:
            return self._confirm_worker(
                employer_mobile=sender_mobile,
                job_id=int(match.group(1)),
                worker_mobile=self._normalize_mobile(match.group(2))
            )

        match = re.fullmatch(r"REJECTWORKER\s+#?(\d+)\s+(\+?\d{10,15})", normalized)
        if match:
            return self._employer_reject_worker(
                employer_mobile=sender_mobile,
                job_id=int(match.group(1)),
                worker_mobile=self._normalize_mobile(match.group(2))
            )

        match = re.fullmatch(r"(ONWAY|ARRIVED|START|COMPLETE)\s+#?(\d+)", normalized)
        if match:
            status_map = {
                "ONWAY": "ON_THE_WAY",
                "ARRIVED": "ARRIVED",
                "START": "WORK_STARTED",
                "COMPLETE": "COMPLETED",
            }
            return self._update_worker_status(
                worker_mobile=sender_mobile,
                job_id=int(match.group(2)),
                new_status=status_map[match.group(1)]
            )

        match = re.fullmatch(r"STATUS\s+#?(\d+)", normalized)
        if match:
            return self._job_status(sender_mobile, int(match.group(1)))

        return None

    def handle_location(
        self,
        worker_mobile: str,
        latitude: float,
        longitude: float
    ) -> Optional[str]:
        assignment = self.repository.record_tracking_location(
            worker_mobile=worker_mobile,
            latitude=latitude,
            longitude=longitude
        )
        if not assignment:
            return None

        job_lat = assignment.get("job_latitude")
        job_lon = assignment.get("job_longitude")
        if job_lat is None or job_lon is None:
            return "📍 Location update save అయింది."

        distance_km = self._distance_km(
            latitude,
            longitude,
            float(job_lat),
            float(job_lon)
        )
        job_id = int(assignment["employer_job_id"])
        status = str(assignment["status"])

        auto_arrived = False
        if (
            distance_km <= self.arrival_radius_km
            and status in {"CONFIRMED", "ON_THE_WAY"}
        ):
            status_result = self.repository.update_worker_status(
                job_id=job_id,
                worker_mobile=worker_mobile,
                new_status="ARRIVED"
            )
            if status_result.get("ok"):
                status = "ARRIVED"
                auto_arrived = True

        worker = self.repository.find_user(worker_mobile) or {}
        worker_name = worker.get("name") or "Worker"
        employer_mobile = str(assignment["employer_mobile"])
        employer_message = (
            f"📍 Worker location update — Job #{job_id}\n\n"
            f"Worker: {worker_name}\n"
            f"Status: {self.STATUS_LABELS.get(status, status)}\n"
            f"Job వరకు distance: {distance_km:.2f} km\n"
            f"Location: https://maps.google.com/?q={latitude:.6f},{longitude:.6f}"
        )
        if auto_arrived:
            employer_message += "\n\n✅ PODX geofence: Worker job locationకి చేరుకున్నారు."
        self._send(employer_mobile, employer_message)

        if auto_arrived:
            return (
                f"✅ Job #{job_id}: మీరు job locationకి చేరుకున్నట్లు PODX గుర్తించింది.\n"
                "Work ప్రారంభించినప్పుడు START " + str(job_id) + " పంపండి."
            )
        return (
            f"📍 Job #{job_id} location update save అయింది.\n"
            f"Job వరకు సుమారు {distance_km:.2f} km."
        )

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
        worker_contact = worker.get("entered_mobile") or worker_mobile
        distance = self._worker_job_distance(worker, job)
        distance_text = f"{distance:.2f} km" if distance is not None else "-"

        employer_message = (
            f"🙋 Worker interested — Job #{job_id}\n\n"
            f"Worker: {worker_name}\n"
            f"Contact: {worker_contact}\n"
            f"Distance: {distance_text}\n\n"
            f"Confirm: CONFIRM {job_id} {worker_mobile}\n"
            f"Reject: REJECTWORKER {job_id} {worker_mobile}"
        )
        self._send(str(job["employer_mobile"]), employer_message)

        return (
            f"✅ Job #{job_id} interest employerకి పంపాం.\n"
            "Employer confirm చేసిన తర్వాత contact number + navigation details వస్తాయి."
        )

    def _reject_invitation(self, worker_mobile: str, job_id: int) -> str:
        result = self.repository.reject_invitation(job_id, worker_mobile)
        if not result.get("ok"):
            return f"❌ Job #{job_id} దొరకలేదు."
        return f"✅ Job #{job_id}ను reject చేశారు."

    def _confirm_worker(
        self,
        employer_mobile: str,
        job_id: int,
        worker_mobile: str
    ) -> str:
        result = self.repository.confirm_worker(
            job_id=job_id,
            employer_mobile=employer_mobile,
            worker_mobile=worker_mobile
        )
        if not result.get("ok"):
            reason = result.get("reason")
            if reason == "NOT_JOB_OWNER":
                return "❌ ఈ Job మీది కాదు."
            if reason == "JOB_ALREADY_FULL":
                return f"⚠️ Job #{job_id} required workers ఇప్పటికే fill అయ్యారు."
            if reason == "ASSIGNMENT_NOT_FOUND":
                return "❌ Worker acceptance దొరకలేదు."
            return f"❌ Job #{job_id} worker confirmation చేయలేకపోయాం."

        job = result["job"]
        worker = result.get("worker") or {}
        worker_name = worker.get("name") or "Worker"
        worker_contact = worker.get("entered_mobile") or worker_mobile
        employer_contact = job.get("employer_contact") or employer_mobile
        lat = job.get("latitude")
        lon = job.get("longitude")
        map_link = "-"
        if lat is not None and lon is not None:
            map_link = f"https://maps.google.com/?q={float(lat):.6f},{float(lon):.6f}"

        worker_message = (
            f"🎉 Job #{job_id} CONFIRMED!\n\n"
            f"పని: {job['service']}\n"
            f"Employer contact: {employer_contact}\n"
            f"Job location: {map_link}\n\n"
            f"బయలుదేరినప్పుడు: ONWAY {job_id}\n"
            f"చేరుకున్నప్పుడు: ARRIVED {job_id}\n"
            f"Work start: START {job_id}\n"
            f"Work complete: COMPLETE {job_id}\n\n"
            "ప్రయాణంలో location share చేస్తే employerకి tracking update వెళ్తుంది."
        )
        self._send(worker_mobile, worker_message)

        confirmed = int(result["confirmed_count"])
        required = int(result["required_workers"])
        filled_text = "\n✅ Required workers filled. Job auto-closed." if result.get("job_filled") else ""
        return (
            f"✅ {worker_name} confirmed — Job #{job_id}\n"
            f"Worker contact: {worker_contact}\n"
            f"Confirmed: {confirmed}/{required}{filled_text}"
        )

    def _employer_reject_worker(
        self,
        employer_mobile: str,
        job_id: int,
        worker_mobile: str
    ) -> str:
        result = self.repository.employer_reject_worker(
            job_id=job_id,
            employer_mobile=employer_mobile,
            worker_mobile=worker_mobile
        )
        if not result.get("ok"):
            return "❌ Worker rejection చేయలేకపోయాం."
        self._send(worker_mobile, f"ℹ️ Job #{job_id}: Employer ఈ requestను confirm చేయలేదు.")
        return f"✅ Job #{job_id}: Worker request rejected."

    def _update_worker_status(
        self,
        worker_mobile: str,
        job_id: int,
        new_status: str
    ) -> str:
        result = self.repository.update_worker_status(
            job_id=job_id,
            worker_mobile=worker_mobile,
            new_status=new_status
        )
        if not result.get("ok"):
            assignment = result.get("assignment") or {}
            current = assignment.get("status")
            if result.get("reason") == "ASSIGNMENT_NOT_FOUND":
                return f"❌ Job #{job_id} confirmed assignment దొరకలేదు."
            return (
                f"⚠️ ఈ status ఇప్పుడు set చేయలేరు. Current status: "
                f"{self.STATUS_LABELS.get(current, current)}"
            )

        job = result["job"]
        worker = self.repository.find_user(worker_mobile) or {}
        worker_name = worker.get("name") or "Worker"
        label = self.STATUS_LABELS.get(new_status, new_status)
        self._send(
            str(job["employer_mobile"]),
            f"🚦 Job #{job_id} worker status update\n\nWorker: {worker_name}\nStatus: {label}"
        )

        next_hint = {
            "ON_THE_WAY": f"Location share చేస్తూ ఉండండి. చేరుకున్నప్పుడు ARRIVED {job_id} పంపండి.",
            "ARRIVED": f"Work ప్రారంభించినప్పుడు START {job_id} పంపండి.",
            "WORK_STARTED": f"పని పూర్తయ్యాక COMPLETE {job_id} పంపండి.",
            "COMPLETED": "✅ Job work completed status save అయింది.",
        }.get(new_status, "")
        return f"✅ Job #{job_id} status: {label}\n{next_hint}".strip()

    def _job_status(self, employer_mobile: str, job_id: int) -> str:
        job = self.repository.find_job(job_id)
        if not job:
            return f"❌ Job #{job_id} దొరకలేదు."
        if str(job["employer_mobile"]) != str(employer_mobile):
            return "❌ ఈ Job status చూడడానికి permission లేదు."
        counts = self.repository.job_status_counts(job_id)
        required = max(1, int(job.get("required_workers") or 1))
        confirmed = counts.get("CONFIRMED_TOTAL", 0)
        return (
            f"📊 Job #{job_id} Status\n\n"
            f"Required: {required}\n"
            f"Confirmed/Active: {confirmed}/{required}\n"
            f"Waiting confirmation: {counts.get('PENDING_CONFIRMATION', 0)}\n"
            f"On the way: {counts.get('ON_THE_WAY', 0)}\n"
            f"Arrived: {counts.get('ARRIVED', 0)}\n"
            f"Work started: {counts.get('WORK_STARTED', 0)}\n"
            f"Completed: {counts.get('COMPLETED', 0)}\n"
            f"Job status: {job['status']}"
        )

    def _send(self, recipient_mobile: str, message: str) -> None:
        self.whatsapp_service.send_text_message(
            recipient_mobile=recipient_mobile,
            message=message
        )

    def _worker_job_distance(self, worker: dict, job: dict) -> Optional[float]:
        if (
            worker.get("latitude") is None
            or worker.get("longitude") is None
            or job.get("latitude") is None
            or job.get("longitude") is None
        ):
            return None
        return self._distance_km(
            float(worker["latitude"]),
            float(worker["longitude"]),
            float(job["latitude"]),
            float(job["longitude"])
        )

    @staticmethod
    def _normalize_mobile(value: str) -> str:
        digits = "".join(character for character in str(value) if character.isdigit())
        if len(digits) == 10:
            return "91" + digits
        return digits

    @staticmethod
    def _distance_km(
        latitude_a: float,
        longitude_a: float,
        latitude_b: float,
        longitude_b: float
    ) -> float:
        earth_radius_km = 6371.0088
        lat1 = radians(latitude_a)
        lat2 = radians(latitude_b)
        delta_lat = radians(latitude_b - latitude_a)
        delta_lon = radians(longitude_b - longitude_a)
        haversine = (
            sin(delta_lat / 2) ** 2
            + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
        )
        return 2 * earth_radius_km * asin(sqrt(haversine))
