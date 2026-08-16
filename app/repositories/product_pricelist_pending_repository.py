"""Pending AI-extracted business price lists waiting for seller confirmation."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class ProductPriceListPendingRepository:
    def __init__(self, db_path: str = "podx.db") -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS product_pricelist_pending (
                    seller_user_id TEXT PRIMARY KEY,
                    items_json TEXT NOT NULL,
                    media_ref TEXT,
                    source_type TEXT NOT NULL DEFAULT 'ai_media',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def save(self, seller_user_id: str, items: list[dict[str, Any]], media_ref: str | None = None,
             source_type: str = "ai_media") -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO product_pricelist_pending(seller_user_id,items_json,media_ref,source_type,created_at,updated_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(seller_user_id) DO UPDATE SET
                    items_json=excluded.items_json, media_ref=excluded.media_ref,
                    source_type=excluded.source_type, updated_at=excluded.updated_at
                """,
                (str(seller_user_id), json.dumps(items, ensure_ascii=False), media_ref, str(source_type), now, now),
            )

    def get(self, seller_user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM product_pricelist_pending WHERE seller_user_id=?",
                (str(seller_user_id),),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["items"] = json.loads(data.pop("items_json") or "[]")
        return data

    def clear(self, seller_user_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM product_pricelist_pending WHERE seller_user_id=?", (str(seller_user_id),))
