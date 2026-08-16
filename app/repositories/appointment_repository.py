class AppointmentRepository:
    def __init__(self, database) -> None:
        self.database = database
        self._ensure_assignment_schema()

    def _ensure_assignment_schema(self) -> None:
        self.database.execute(
            """
            CREATE TABLE IF NOT EXISTS appointment_assignments (
                request_id INTEGER PRIMARY KEY,
                provider_mobile TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'CONFIRMED',
                confirmed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT
            )
            """
        )
        self.database.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_appointment_assignment_provider
            ON appointment_assignments(provider_mobile, status)
            """
        )

    def create_request(
        self,
        customer_mobile: str,
        category: str,
        area: str,
        preferred_date: str,
        preferred_time: str,
    ) -> dict:
        cursor = self.database.execute(
            """
            INSERT INTO appointment_requests (
                customer_mobile,
                category,
                area,
                preferred_date,
                preferred_time,
                status
            ) VALUES (?, ?, ?, ?, ?, 'REQUESTED')
            """,
            (
                customer_mobile,
                category,
                area,
                preferred_date,
                preferred_time,
            ),
        )
        return {
            "id": cursor.lastrowid,
            "customer_mobile": customer_mobile,
            "category": category,
            "area": area,
            "preferred_date": preferred_date,
            "preferred_time": preferred_time,
            "status": "REQUESTED",
        }

    def get_request(self, request_id: int) -> dict | None:
        rows = self.database.fetchall(
            """
            SELECT id, customer_mobile, category, area, preferred_date,
                   preferred_time, status
            FROM appointment_requests
            WHERE id = ?
            LIMIT 1
            """,
            (int(request_id),),
        )
        return dict(rows[0]) if rows else None

    def get_assignment(self, request_id: int) -> dict | None:
        rows = self.database.fetchall(
            """
            SELECT request_id, provider_mobile, status, confirmed_at, completed_at
            FROM appointment_assignments
            WHERE request_id = ?
            LIMIT 1
            """,
            (int(request_id),),
        )
        return dict(rows[0]) if rows else None

    def claim_provider(self, request_id: int, provider_mobile: str) -> bool:
        request = self.get_request(int(request_id))
        if not request or str(request.get("status") or "").upper() != "REQUESTED":
            return False
        cursor = self.database.execute(
            """
            INSERT OR IGNORE INTO appointment_assignments(
                request_id, provider_mobile, status, confirmed_at
            ) VALUES (?, ?, 'CONFIRMED', CURRENT_TIMESTAMP)
            """,
            (int(request_id), str(provider_mobile)),
        )
        created = int(getattr(cursor, "rowcount", 0) or 0) > 0
        if created:
            self.database.execute(
                "UPDATE appointment_requests SET status='CONFIRMED' WHERE id=? AND status='REQUESTED'",
                (int(request_id),),
            )
        return created

    def mark_completed(self, request_id: int, provider_mobile: str) -> bool:
        assignment = self.get_assignment(int(request_id))
        if not assignment or str(assignment.get("provider_mobile")) != str(provider_mobile):
            return False
        if str(assignment.get("status") or "").upper() == "COMPLETED":
            return True
        cursor = self.database.execute(
            """
            UPDATE appointment_assignments
            SET status='COMPLETED', completed_at=CURRENT_TIMESTAMP
            WHERE request_id=? AND provider_mobile=? AND status='CONFIRMED'
            """,
            (int(request_id), str(provider_mobile)),
        )
        updated = int(getattr(cursor, "rowcount", 0) or 0) > 0
        if updated:
            self.database.execute(
                "UPDATE appointment_requests SET status='COMPLETED' WHERE id=?",
                (int(request_id),),
            )
        return updated
