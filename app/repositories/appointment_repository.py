class AppointmentRepository:
    ACTIVE_REQUEST_STATUSES = (
        "REQUESTED",
        "PROVIDER_ACCEPTED",
        "CONFIRMED",
        "RESCHEDULE_REQUESTED",
    )

    def __init__(self, database) -> None:
        self.database = database
        self._ensure_assignment_schema()

    def _ensure_assignment_schema(self) -> None:
        self.database.execute(
            """
            CREATE TABLE IF NOT EXISTS appointment_assignments (
                request_id INTEGER PRIMARY KEY,
                provider_mobile TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PROVIDER_ACCEPTED',
                confirmed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                customer_confirmed_at TEXT,
                cancelled_at TEXT,
                previous_date TEXT,
                previous_time TEXT,
                reschedule_requested_at TEXT
            )
            """
        )
        existing = {
            str(row["name"])
            for row in self.database.fetchall("PRAGMA table_info(appointment_assignments)")
        }
        additions = {
            "customer_confirmed_at": "TEXT",
            "cancelled_at": "TEXT",
            "previous_date": "TEXT",
            "previous_time": "TEXT",
            "reschedule_requested_at": "TEXT",
        }
        for column, definition in additions.items():
            if column not in existing:
                self.database.execute(
                    f"ALTER TABLE appointment_assignments ADD COLUMN {column} {definition}"
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
            (customer_mobile, category, area, preferred_date, preferred_time),
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
            SELECT request_id, provider_mobile, status, confirmed_at, completed_at,
                   customer_confirmed_at, cancelled_at, previous_date, previous_time,
                   reschedule_requested_at
            FROM appointment_assignments
            WHERE request_id = ?
            LIMIT 1
            """,
            (int(request_id),),
        )
        return dict(rows[0]) if rows else None

    def latest_customer_request(self, customer_mobile: str, statuses=None) -> dict | None:
        wanted = tuple(statuses or self.ACTIVE_REQUEST_STATUSES)
        if not wanted:
            return None
        placeholders = ",".join("?" for _ in wanted)
        rows = self.database.fetchall(
            f"""
            SELECT id, customer_mobile, category, area, preferred_date,
                   preferred_time, status
            FROM appointment_requests
            WHERE customer_mobile = ? AND status IN ({placeholders})
            ORDER BY id DESC LIMIT 1
            """,
            (str(customer_mobile), *wanted),
        )
        return dict(rows[0]) if rows else None

    def latest_provider_assignment(self, provider_mobile: str, statuses=None) -> dict | None:
        wanted = tuple(statuses or ("PROVIDER_ACCEPTED", "CONFIRMED", "RESCHEDULE_REQUESTED"))
        placeholders = ",".join("?" for _ in wanted)
        rows = self.database.fetchall(
            f"""
            SELECT a.request_id, a.provider_mobile, a.status, a.confirmed_at,
                   a.completed_at, a.customer_confirmed_at, a.cancelled_at,
                   a.previous_date, a.previous_time, a.reschedule_requested_at
            FROM appointment_assignments a
            WHERE a.provider_mobile = ? AND a.status IN ({placeholders})
            ORDER BY a.request_id DESC LIMIT 1
            """,
            (str(provider_mobile), *wanted),
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
            ) VALUES (?, ?, 'PROVIDER_ACCEPTED', CURRENT_TIMESTAMP)
            """,
            (int(request_id), str(provider_mobile)),
        )
        created = int(getattr(cursor, "rowcount", 0) or 0) > 0
        if created:
            self.database.execute(
                """
                UPDATE appointment_requests
                SET status='PROVIDER_ACCEPTED'
                WHERE id=? AND status='REQUESTED'
                """,
                (int(request_id),),
            )
        return created

    def customer_confirm(self, request_id: int, customer_mobile: str) -> bool:
        request = self.get_request(int(request_id))
        assignment = self.get_assignment(int(request_id))
        if not request or not assignment:
            return False
        if str(request.get("customer_mobile")) != str(customer_mobile):
            return False
        request_status = str(request.get("status") or "").upper()
        assignment_status = str(assignment.get("status") or "").upper()
        if request_status == "CONFIRMED" and assignment.get("customer_confirmed_at"):
            return True
        # Compatibility for appointments accepted before two-sided confirmation existed.
        if request_status == "CONFIRMED" and assignment_status == "CONFIRMED":
            cursor = self.database.execute(
                """
                UPDATE appointment_assignments
                SET customer_confirmed_at=CURRENT_TIMESTAMP
                WHERE request_id=? AND customer_confirmed_at IS NULL
                """,
                (int(request_id),),
            )
            return int(getattr(cursor, "rowcount", 0) or 0) > 0
        if request_status != "PROVIDER_ACCEPTED" or assignment_status != "PROVIDER_ACCEPTED":
            return False
        self.database.execute(
            """
            UPDATE appointment_assignments
            SET status='CONFIRMED', customer_confirmed_at=CURRENT_TIMESTAMP
            WHERE request_id=? AND status='PROVIDER_ACCEPTED'
            """,
            (int(request_id),),
        )
        cursor = self.database.execute(
            """
            UPDATE appointment_requests
            SET status='CONFIRMED'
            WHERE id=? AND customer_mobile=? AND status='PROVIDER_ACCEPTED'
            """,
            (int(request_id), str(customer_mobile)),
        )
        return int(getattr(cursor, "rowcount", 0) or 0) > 0

    def cancel_request(self, request_id: int, customer_mobile: str) -> bool:
        request = self.get_request(int(request_id))
        if not request or str(request.get("customer_mobile")) != str(customer_mobile):
            return False
        status = str(request.get("status") or "").upper()
        if status == "CANCELLED":
            return True
        if status not in self.ACTIVE_REQUEST_STATUSES:
            return False
        cursor = self.database.execute(
            """
            UPDATE appointment_requests SET status='CANCELLED'
            WHERE id=? AND customer_mobile=? AND status IN ('REQUESTED','PROVIDER_ACCEPTED','CONFIRMED','RESCHEDULE_REQUESTED')
            """,
            (int(request_id), str(customer_mobile)),
        )
        if int(getattr(cursor, "rowcount", 0) or 0) > 0:
            self.database.execute(
                """
                UPDATE appointment_assignments
                SET status='CANCELLED', cancelled_at=CURRENT_TIMESTAMP
                WHERE request_id=? AND status <> 'COMPLETED'
                """,
                (int(request_id),),
            )
            return True
        return False

    def request_reschedule(
        self,
        request_id: int,
        customer_mobile: str,
        preferred_date: str,
        preferred_time: str,
    ) -> bool:
        request = self.get_request(int(request_id))
        assignment = self.get_assignment(int(request_id))
        if not request or not assignment:
            return False
        if str(request.get("customer_mobile")) != str(customer_mobile):
            return False
        # Rescheduling is only available after both parties confirmed the original slot.
        if str(request.get("status") or "").upper() != "CONFIRMED" or not assignment.get("customer_confirmed_at"):
            return False
        self.database.execute(
            """
            UPDATE appointment_assignments
            SET status='RESCHEDULE_REQUESTED', previous_date=?, previous_time=?,
                reschedule_requested_at=CURRENT_TIMESTAMP, customer_confirmed_at=NULL
            WHERE request_id=?
            """,
            (request.get("preferred_date"), request.get("preferred_time"), int(request_id)),
        )
        cursor = self.database.execute(
            """
            UPDATE appointment_requests
            SET preferred_date=?, preferred_time=?, status='RESCHEDULE_REQUESTED'
            WHERE id=? AND customer_mobile=?
            """,
            (preferred_date, preferred_time, int(request_id), str(customer_mobile)),
        )
        return int(getattr(cursor, "rowcount", 0) or 0) > 0

    def provider_accept_reschedule(self, request_id: int, provider_mobile: str) -> bool:
        request = self.get_request(int(request_id))
        assignment = self.get_assignment(int(request_id))
        if not request or not assignment:
            return False
        if str(assignment.get("provider_mobile")) != str(provider_mobile):
            return False
        if str(request.get("status") or "").upper() == "CONFIRMED" and str(assignment.get("status") or "").upper() == "CONFIRMED" and assignment.get("customer_confirmed_at"):
            return True
        if str(request.get("status") or "").upper() != "RESCHEDULE_REQUESTED":
            return False
        self.database.execute(
            """
            UPDATE appointment_assignments
            SET status='CONFIRMED', customer_confirmed_at=CURRENT_TIMESTAMP
            WHERE request_id=? AND provider_mobile=? AND status='RESCHEDULE_REQUESTED'
            """,
            (int(request_id), str(provider_mobile)),
        )
        cursor = self.database.execute(
            "UPDATE appointment_requests SET status='CONFIRMED' WHERE id=? AND status='RESCHEDULE_REQUESTED'",
            (int(request_id),),
        )
        return int(getattr(cursor, "rowcount", 0) or 0) > 0

    def provider_decline_reschedule(self, request_id: int, provider_mobile: str) -> bool:
        request = self.get_request(int(request_id))
        assignment = self.get_assignment(int(request_id))
        if not request or not assignment or str(assignment.get("provider_mobile")) != str(provider_mobile):
            return False
        if str(request.get("status") or "").upper() != "RESCHEDULE_REQUESTED":
            return False
        previous_date = assignment.get("previous_date") or request.get("preferred_date")
        previous_time = assignment.get("previous_time") or request.get("preferred_time")
        self.database.execute(
            """
            UPDATE appointment_assignments
            SET status='CONFIRMED', customer_confirmed_at=CURRENT_TIMESTAMP
            WHERE request_id=? AND provider_mobile=?
            """,
            (int(request_id), str(provider_mobile)),
        )
        self.database.execute(
            """
            UPDATE appointment_requests
            SET preferred_date=?, preferred_time=?, status='CONFIRMED'
            WHERE id=?
            """,
            (previous_date, previous_time, int(request_id)),
        )
        return True

    def mark_completed(self, request_id: int, provider_mobile: str) -> bool:
        assignment = self.get_assignment(int(request_id))
        if not assignment or str(assignment.get("provider_mobile")) != str(provider_mobile):
            return False
        if str(assignment.get("status") or "").upper() == "COMPLETED":
            return True
        if not assignment.get("customer_confirmed_at"):
            return False
        cursor = self.database.execute(
            """
            UPDATE appointment_assignments
            SET status='COMPLETED', completed_at=CURRENT_TIMESTAMP
            WHERE request_id=? AND provider_mobile=? AND status='CONFIRMED' AND customer_confirmed_at IS NOT NULL
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
