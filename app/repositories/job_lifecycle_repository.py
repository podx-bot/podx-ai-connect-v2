from typing import Optional

from app.database.database import Database


class JobLifecycleRepository:
    ACTIVE_WORKER_STATUSES = (
        "PENDING_CONFIRMATION",
        "CONFIRMED",
        "ON_THE_WAY",
        "ARRIVED",
        "WORK_STARTED",
    )

    def __init__(self, database: Database) -> None:
        self.database = database

    def find_job(self, job_id: int) -> Optional[dict]:
        row = self.database.fetchone(
            "SELECT * FROM employer_jobs WHERE id = ?",
            (job_id,)
        )
        return dict(row) if row else None

    def find_user(self, whatsapp_mobile: str) -> Optional[dict]:
        row = self.database.fetchone(
            "SELECT * FROM users WHERE whatsapp_mobile = ?",
            (whatsapp_mobile,)
        )
        return dict(row) if row else None

    def accept_job(self, job_id: int, worker_mobile: str) -> dict:
        job = self.find_job(job_id)
        if not job:
            return {"ok": False, "reason": "JOB_NOT_FOUND"}
        if job["status"] not in {"OPEN", "FILLED"}:
            return {"ok": False, "reason": "JOB_NOT_OPEN", "job": job}
        if str(job["employer_mobile"]) == str(worker_mobile):
            return {"ok": False, "reason": "SELF_ACCEPT", "job": job}

        existing = self.find_assignment(job_id, worker_mobile)
        if existing and existing["status"] not in {"REJECTED", "CANCELLED"}:
            return {
                "ok": True,
                "reason": "ALREADY_ACCEPTED",
                "job": job,
                "assignment": existing,
            }

        worker = self.find_user(worker_mobile) or {}
        worker_contact = worker.get("entered_mobile") or worker_mobile
        self.database.execute(
            """
            INSERT INTO job_assignments (
                employer_job_id,
                worker_mobile,
                status,
                worker_contact,
                accepted_at,
                updated_at
            )
            VALUES (?, ?, 'PENDING_CONFIRMATION', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(employer_job_id, worker_mobile)
            DO UPDATE SET
                status = 'PENDING_CONFIRMATION',
                worker_contact = excluded.worker_contact,
                accepted_at = CURRENT_TIMESTAMP,
                confirmed_at = NULL,
                arrived_at = NULL,
                work_started_at = NULL,
                completed_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            """,
            (job_id, worker_mobile, worker_contact)
        )
        return {
            "ok": True,
            "reason": "ACCEPTED",
            "job": job,
            "assignment": self.find_assignment(job_id, worker_mobile),
            "worker": worker,
        }

    def reject_invitation(self, job_id: int, worker_mobile: str) -> dict:
        job = self.find_job(job_id)
        if not job:
            return {"ok": False, "reason": "JOB_NOT_FOUND"}
        self.database.execute(
            """
            INSERT INTO job_assignments (
                employer_job_id, worker_mobile, status, updated_at
            )
            VALUES (?, ?, 'REJECTED', CURRENT_TIMESTAMP)
            ON CONFLICT(employer_job_id, worker_mobile)
            DO UPDATE SET status = 'REJECTED', updated_at = CURRENT_TIMESTAMP
            """,
            (job_id, worker_mobile)
        )
        return {"ok": True, "job": job}

    def find_assignment(
        self,
        job_id: int,
        worker_mobile: str
    ) -> Optional[dict]:
        row = self.database.fetchone(
            """
            SELECT * FROM job_assignments
            WHERE employer_job_id = ? AND worker_mobile = ?
            """,
            (job_id, worker_mobile)
        )
        return dict(row) if row else None

    def confirm_worker(
        self,
        job_id: int,
        employer_mobile: str,
        worker_mobile: str
    ) -> dict:
        job = self.find_job(job_id)
        if not job:
            return {"ok": False, "reason": "JOB_NOT_FOUND"}
        if str(job["employer_mobile"]) != str(employer_mobile):
            return {"ok": False, "reason": "NOT_JOB_OWNER", "job": job}

        assignment = self.find_assignment(job_id, worker_mobile)
        if not assignment:
            return {"ok": False, "reason": "ASSIGNMENT_NOT_FOUND", "job": job}
        if assignment["status"] == "CONFIRMED":
            return self._confirmation_result(job, assignment)
        if assignment["status"] != "PENDING_CONFIRMATION":
            return {
                "ok": False,
                "reason": "INVALID_ASSIGNMENT_STATUS",
                "job": job,
                "assignment": assignment,
            }

        required_workers = max(1, int(job.get("required_workers") or 1))
        if self.count_confirmed(job_id) >= required_workers:
            self._mark_job_filled(job_id)
            return {"ok": False, "reason": "JOB_ALREADY_FULL", "job": self.find_job(job_id)}

        self.database.execute(
            """
            UPDATE job_assignments
            SET status = 'CONFIRMED',
                confirmed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE employer_job_id = ? AND worker_mobile = ?
            """,
            (job_id, worker_mobile)
        )
        assignment = self.find_assignment(job_id, worker_mobile)
        result = self._confirmation_result(job, assignment)

        if result["confirmed_count"] >= result["required_workers"]:
            self._mark_job_filled(job_id)
            result["job"] = self.find_job(job_id)
            result["job_filled"] = True
        else:
            result["job_filled"] = False
        return result

    def employer_reject_worker(
        self,
        job_id: int,
        employer_mobile: str,
        worker_mobile: str
    ) -> dict:
        job = self.find_job(job_id)
        if not job:
            return {"ok": False, "reason": "JOB_NOT_FOUND"}
        if str(job["employer_mobile"]) != str(employer_mobile):
            return {"ok": False, "reason": "NOT_JOB_OWNER", "job": job}
        assignment = self.find_assignment(job_id, worker_mobile)
        if not assignment:
            return {"ok": False, "reason": "ASSIGNMENT_NOT_FOUND", "job": job}
        self.database.execute(
            """
            UPDATE job_assignments
            SET status = 'REJECTED', updated_at = CURRENT_TIMESTAMP
            WHERE employer_job_id = ? AND worker_mobile = ?
            """,
            (job_id, worker_mobile)
        )
        return {"ok": True, "job": job, "assignment": self.find_assignment(job_id, worker_mobile)}

    def update_worker_status(
        self,
        job_id: int,
        worker_mobile: str,
        new_status: str
    ) -> dict:
        assignment = self.find_assignment(job_id, worker_mobile)
        if not assignment:
            return {"ok": False, "reason": "ASSIGNMENT_NOT_FOUND"}

        allowed_transitions = {
            "CONFIRMED": {"ON_THE_WAY", "ARRIVED"},
            "ON_THE_WAY": {"ARRIVED"},
            "ARRIVED": {"WORK_STARTED"},
            "WORK_STARTED": {"COMPLETED"},
        }
        current = assignment["status"]
        if new_status == current:
            return {"ok": True, "reason": "NO_CHANGE", "assignment": assignment, "job": self.find_job(job_id)}
        if new_status not in allowed_transitions.get(current, set()):
            return {
                "ok": False,
                "reason": "INVALID_TRANSITION",
                "assignment": assignment,
                "job": self.find_job(job_id),
            }

        timestamp_column = {
            "ARRIVED": "arrived_at",
            "WORK_STARTED": "work_started_at",
            "COMPLETED": "completed_at",
        }.get(new_status)
        if timestamp_column:
            self.database.execute(
                f"""
                UPDATE job_assignments
                SET status = ?,
                    {timestamp_column} = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE employer_job_id = ? AND worker_mobile = ?
                """,
                (new_status, job_id, worker_mobile)
            )
        else:
            self.database.execute(
                """
                UPDATE job_assignments
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE employer_job_id = ? AND worker_mobile = ?
                """,
                (new_status, job_id, worker_mobile)
            )
        return {
            "ok": True,
            "reason": "UPDATED",
            "assignment": self.find_assignment(job_id, worker_mobile),
            "job": self.find_job(job_id),
        }

    def active_assignment_for_worker(self, worker_mobile: str) -> Optional[dict]:
        placeholders = ",".join("?" for _ in self.ACTIVE_WORKER_STATUSES)
        row = self.database.fetchone(
            f"""
            SELECT a.*, j.employer_mobile, j.service, j.requirement,
                   j.latitude AS job_latitude, j.longitude AS job_longitude,
                   j.location_name AS job_location_name,
                   j.location_address AS job_location_address,
                   j.employer_contact, j.required_workers, j.status AS job_status
            FROM job_assignments a
            JOIN employer_jobs j ON j.id = a.employer_job_id
            WHERE a.worker_mobile = ?
              AND a.status IN ({placeholders})
            ORDER BY a.updated_at DESC
            LIMIT 1
            """,
            (worker_mobile, *self.ACTIVE_WORKER_STATUSES)
        )
        return dict(row) if row else None

    def record_tracking_location(
        self,
        worker_mobile: str,
        latitude: float,
        longitude: float
    ) -> Optional[dict]:
        assignment = self.active_assignment_for_worker(worker_mobile)
        if not assignment:
            return None
        job_id = int(assignment["employer_job_id"])
        self.database.execute(
            """
            UPDATE job_assignments
            SET last_latitude = ?,
                last_longitude = ?,
                last_location_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE employer_job_id = ? AND worker_mobile = ?
            """,
            (latitude, longitude, job_id, worker_mobile)
        )
        self.database.execute(
            """
            INSERT INTO worker_tracking_updates (
                employer_job_id, worker_mobile, latitude, longitude, worker_status
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (job_id, worker_mobile, latitude, longitude, assignment["status"])
        )
        refreshed = self.active_assignment_for_worker(worker_mobile)
        return refreshed

    def count_confirmed(self, job_id: int) -> int:
        row = self.database.fetchone(
            """
            SELECT COUNT(*) AS total
            FROM job_assignments
            WHERE employer_job_id = ?
              AND status IN ('CONFIRMED', 'ON_THE_WAY', 'ARRIVED', 'WORK_STARTED', 'COMPLETED')
            """,
            (job_id,)
        )
        return int(row["total"] if row else 0)

    def job_status_counts(self, job_id: int) -> dict:
        rows = self.database.fetchall(
            """
            SELECT status, COUNT(*) AS total
            FROM job_assignments
            WHERE employer_job_id = ?
            GROUP BY status
            """,
            (job_id,)
        )
        result = {str(row["status"]): int(row["total"]) for row in rows}
        result["CONFIRMED_TOTAL"] = self.count_confirmed(job_id)
        return result

    def _confirmation_result(self, job: dict, assignment: dict) -> dict:
        worker = self.find_user(str(assignment["worker_mobile"])) or {}
        confirmed = self.count_confirmed(int(job["id"]))
        required = max(1, int(job.get("required_workers") or 1))
        return {
            "ok": True,
            "job": job,
            "assignment": assignment,
            "worker": worker,
            "confirmed_count": confirmed,
            "required_workers": required,
        }

    def _mark_job_filled(self, job_id: int) -> None:
        self.database.execute(
            """
            UPDATE employer_jobs
            SET status = 'FILLED', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (job_id,)
        )
