import json
from typing import Any


class DemandRepository:
    VALID_STATUSES = {"OPEN", "MATCHED", "RESOLVED", "EXPIRED"}

    def __init__(self, database) -> None:
        self.database = database
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.database.execute(
            """
            CREATE TABLE IF NOT EXISTS universal_demands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_mobile TEXT NOT NULL,
                intent TEXT NOT NULL,
                category TEXT,
                location_text TEXT,
                source_message TEXT NOT NULL,
                structured_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'OPEN',
                resolution_type TEXT,
                resolution_ref TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                resolved_at TEXT
            )
            """
        )
        self.database.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_universal_demands_status_category
            ON universal_demands(status, category)
            """
        )
        self.database.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_universal_demands_mobile_status
            ON universal_demands(user_mobile, status)
            """
        )

    def create(
        self,
        *,
        user_mobile: str,
        intent: str,
        source_message: str,
        category: str | None = None,
        location_text: str | None = None,
        structured_fields: dict[str, Any] | None = None,
        status: str = "OPEN",
    ) -> dict:
        normalized_status = str(status or "OPEN").upper()
        if normalized_status not in self.VALID_STATUSES:
            raise ValueError(f"Unsupported demand status: {status}")
        payload = json.dumps(structured_fields or {}, ensure_ascii=False, sort_keys=True)
        cursor = self.database.execute(
            """
            INSERT INTO universal_demands (
                user_mobile, intent, category, location_text,
                source_message, structured_json, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_mobile,
                str(intent or "UNKNOWN").upper(),
                category,
                location_text,
                source_message,
                payload,
                normalized_status,
            ),
        )
        return self.get(cursor.lastrowid)

    def get(self, demand_id: int) -> dict | None:
        row = self.database.fetchone(
            "SELECT * FROM universal_demands WHERE id = ?",
            (demand_id,),
        )
        return self._to_dict(row) if row else None

    def list_open(self, limit: int = 100) -> list[dict]:
        rows = self.database.fetchall(
            """
            SELECT * FROM universal_demands
            WHERE status = 'OPEN'
            ORDER BY created_at ASC, id ASC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        )
        return [self._to_dict(row) for row in rows]

    def top_open_clusters(self, limit: int = 10) -> list[dict]:
        rows = self.database.fetchall(
            """
            SELECT
                COALESCE(NULLIF(category, ''), intent) AS demand_key,
                COALESCE(NULLIF(location_text, ''), '-') AS location_text,
                COUNT(*) AS demand_count,
                MIN(created_at) AS first_seen_at,
                MAX(created_at) AS last_seen_at
            FROM universal_demands
            WHERE status = 'OPEN'
            GROUP BY demand_key, COALESCE(NULLIF(location_text, ''), '-')
            ORDER BY demand_count DESC, last_seen_at DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        )
        return [dict(row) for row in rows]

    def update_status(
        self,
        demand_id: int,
        status: str,
        *,
        resolution_type: str | None = None,
        resolution_ref: str | None = None,
    ) -> dict | None:
        normalized_status = str(status or "").upper()
        if normalized_status not in self.VALID_STATUSES:
            raise ValueError(f"Unsupported demand status: {status}")
        resolved_expression = "CURRENT_TIMESTAMP" if normalized_status == "RESOLVED" else "resolved_at"
        self.database.execute(
            f"""
            UPDATE universal_demands
            SET status = ?,
                resolution_type = ?,
                resolution_ref = ?,
                updated_at = CURRENT_TIMESTAMP,
                resolved_at = {resolved_expression}
            WHERE id = ?
            """,
            (normalized_status, resolution_type, resolution_ref, demand_id),
        )
        return self.get(demand_id)

    @staticmethod
    def _to_dict(row) -> dict:
        result = dict(row)
        try:
            result["structured_fields"] = json.loads(result.pop("structured_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            result["structured_fields"] = {}
            result.pop("structured_json", None)
        return result
