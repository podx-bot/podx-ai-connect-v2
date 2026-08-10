from math import asin, cos, radians, sin, sqrt
from typing import Any

from app.repositories.user_repository import UserRepository
from app.whatsapp.whatsapp_service import WhatsAppService


class JobMatchingService:
    def __init__(
        self,
        user_repository: UserRepository,
        whatsapp_service: WhatsAppService,
        max_distance_km: float = 25.0
    ) -> None:
        self.user_repository = user_repository
        self.whatsapp_service = whatsapp_service
        self.max_distance_km = float(max_distance_km)

    def match_and_notify(self, job: dict[str, Any]) -> dict[str, Any]:
        candidates = self.user_repository.find_candidate_workers(str(job["service"]))
        matched = []
        notified = []
        skipped_self = 0

        for worker in candidates:
            worker_mobile = str(worker["whatsapp_mobile"])
            if worker_mobile == str(job["employer_mobile"]):
                skipped_self += 1
                continue

            distance_km = self._distance_km(
                float(job["latitude"]),
                float(job["longitude"]),
                float(worker["latitude"]),
                float(worker["longitude"])
            )
            if distance_km > self.max_distance_km:
                continue

            matched.append({
                "worker_mobile": worker_mobile,
                "distance_km": round(distance_km, 2),
                "availability": worker.get("availability"),
                "experience": worker.get("experience")
            })

            if self.user_repository.has_match_notification(int(job["id"]), worker_mobile):
                continue

            message = self._worker_message(job, worker, distance_km)
            send_result = self.whatsapp_service.send_text_message(
                recipient_mobile=worker_mobile,
                message=message
            )
            if not send_result.get("success"):
                continue

            self.user_repository.record_match_notification(
                employer_job_id=int(job["id"]),
                worker_mobile=worker_mobile,
                distance_km=distance_km,
                provider_message_id=send_result.get("provider_message_id")
            )
            notified.append({
                "worker_mobile": worker_mobile,
                "distance_km": round(distance_km, 2),
                "provider_message_id": send_result.get("provider_message_id")
            })

        return {
            "candidate_count": len(candidates),
            "matched_count": len(matched),
            "notified_count": len(notified),
            "skipped_self_count": skipped_self,
            "matched": matched,
            "notified": notified
        }

    def _worker_message(
        self,
        job: dict[str, Any],
        worker: dict[str, Any],
        distance_km: float
    ) -> str:
        job_id = int(job["id"])
        required_workers = max(1, int(job.get("required_workers") or 1))
        return (
            "🔔 మీ దగ్గర పని వచ్చింది!\n\n"
            f"పని: {job['service']}\n"
            f"వివరాలు: {job['requirement']}\n"
            f"కావాల్సిన వాళ్లు: {required_workers}\n"
            f"దూరం: సుమారు {distance_km:.1f} km\n\n"
            "ఈ పని చేయడానికి ఇష్టమేనా?\n\n"
            "1. అవును ✅\n"
            "2. వద్దు ❌\n\n"
            "1 లేదా 2 పంపండి."
            f"\n(లేదా ACCEPT {job_id} / REJECT {job_id})"
        )

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
