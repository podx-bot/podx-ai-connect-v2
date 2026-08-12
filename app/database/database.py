import sqlite3
import threading
from pathlib import Path
from typing import Iterable, Optional


class Database:
    def __init__(self, database_path: str) -> None:
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self.connection = sqlite3.connect(
            str(path),
            check_same_thread=False
        )
        self.connection.row_factory = sqlite3.Row

    def execute(
        self,
        query: str,
        parameters: Iterable = ()
    ) -> sqlite3.Cursor:
        with self._lock:
            cursor = self.connection.execute(
                query,
                tuple(parameters)
            )
            self.connection.commit()
            return cursor

    def fetchone(
        self,
        query: str,
        parameters: Iterable = ()
    ) -> Optional[sqlite3.Row]:
        with self._lock:
            return self.connection.execute(
                query,
                tuple(parameters)
            ).fetchone()

    def fetchall(
        self,
        query: str,
        parameters: Iterable = ()
    ) -> list[sqlite3.Row]:
        with self._lock:
            return self.connection.execute(
                query,
                tuple(parameters)
            ).fetchall()

    def _column_exists(
        self,
        table_name: str,
        column_name: str
    ) -> bool:
        rows = self.fetchall(f"PRAGMA table_info({table_name})")
        return any(row["name"] == column_name for row in rows)

    def _add_column_if_missing(
        self,
        table_name: str,
        column_name: str,
        column_definition: str
    ) -> None:
        if self._column_exists(table_name, column_name):
            return
        self.execute(
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name} {column_definition}"
        )

    def create_tables(self) -> None:
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                whatsapp_mobile TEXT UNIQUE NOT NULL,
                entered_mobile TEXT,
                name TEXT,
                language TEXT,
                area TEXT,
                latitude REAL,
                longitude REAL,
                location_name TEXT,
                location_address TEXT,
                location_updated_at TEXT,
                role TEXT,
                job_category TEXT,
                experience TEXT,
                availability TEXT,
                worker_registration_complete INTEGER NOT NULL DEFAULT 0,
                registration_complete INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        migrations = {
            "latitude": "REAL",
            "longitude": "REAL",
            "location_name": "TEXT",
            "location_address": "TEXT",
            "location_updated_at": "TEXT",
            "role": "TEXT",
            "job_category": "TEXT",
            "experience": "TEXT",
            "availability": "TEXT",
            "worker_registration_complete": "INTEGER NOT NULL DEFAULT 0"
        }
        for column_name, definition in migrations.items():
            self._add_column_if_missing("users", column_name, definition)

        self.execute(
            """
            CREATE TABLE IF NOT EXISTS employer_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employer_mobile TEXT NOT NULL,
                service TEXT NOT NULL,
                requirement TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                location_name TEXT,
                location_address TEXT,
                status TEXT NOT NULL DEFAULT 'DRAFT',
                required_workers INTEGER NOT NULL DEFAULT 1,
                employer_contact TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._add_column_if_missing(
            "employer_jobs", "required_workers", "INTEGER NOT NULL DEFAULT 1"
        )
        self._add_column_if_missing(
            "employer_jobs", "employer_contact", "TEXT"
        )

        self.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_employer_jobs_mobile_status
            ON employer_jobs(employer_mobile, status)
            """
        )

        self.execute(
            """
            CREATE TABLE IF NOT EXISTS match_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employer_job_id INTEGER NOT NULL,
                worker_mobile TEXT NOT NULL,
                distance_km REAL NOT NULL,
                provider_message_id TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(employer_job_id, worker_mobile)
            )
            """
        )

        self.execute(
            """
            CREATE TABLE IF NOT EXISTS job_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employer_job_id INTEGER NOT NULL,
                worker_mobile TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING_CONFIRMATION',
                worker_contact TEXT,
                last_latitude REAL,
                last_longitude REAL,
                last_location_at TEXT,
                accepted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                confirmed_at TEXT,
                arrived_at TEXT,
                work_started_at TEXT,
                completed_at TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(employer_job_id, worker_mobile)
            )
            """
        )
        self.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_job_assignments_job_status
            ON job_assignments(employer_job_id, status)
            """
        )
        self.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_job_assignments_worker_status
            ON job_assignments(worker_mobile, status)
            """
        )

        self.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_tracking_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employer_job_id INTEGER NOT NULL,
                worker_mobile TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                worker_status TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        self.execute(
            """
            CREATE TABLE IF NOT EXISTS appointment_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_mobile TEXT NOT NULL,
                category TEXT NOT NULL,
                area TEXT NOT NULL,
                preferred_date TEXT NOT NULL,
                preferred_time TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'REQUESTED',
                business_id INTEGER,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_appointment_requests_customer_status
            ON appointment_requests(customer_mobile, status)
            """
        )

        self.execute(
            """
            CREATE TABLE IF NOT EXISTS inbound_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_message_id TEXT UNIQUE NOT NULL,
                sender_mobile TEXT NOT NULL,
                message_text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        self.execute(
            """
            CREATE TABLE IF NOT EXISTS delivery_statuses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_message_id TEXT NOT NULL,
                recipient_mobile TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        self.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_sessions (
                sender_mobile TEXT PRIMARY KEY,
                step TEXT NOT NULL DEFAULT 'START',
                data_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def health_check(self) -> bool:
        row = self.fetchone("SELECT 1 AS ok")
        return bool(row and row["ok"] == 1)

    def close(self) -> None:
        with self._lock:
            self.connection.close()
