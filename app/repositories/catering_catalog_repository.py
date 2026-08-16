"""Caterer item/service catalog used for RFQ matching."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List


class CateringCatalogRepository:
    def __init__(self, db_path: str = "podx.db") -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS catering_profiles (
                    provider_user_id TEXT PRIMARY KEY,
                    business_name TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS catering_catalog_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_user_id TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    category TEXT,
                    default_price REAL,
                    price_basis TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    source TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(provider_user_id, normalized_name)
                );
                CREATE INDEX IF NOT EXISTS idx_catering_item_norm ON catering_catalog_items(normalized_name, active);
                """
            )

    def enable_provider(self, provider_user_id: str, business_name: str | None = None) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO catering_profiles(provider_user_id,business_name,active,created_at,updated_at)
                   VALUES(?,?,1,?,?)
                   ON CONFLICT(provider_user_id) DO UPDATE SET
                     business_name=COALESCE(excluded.business_name,catering_profiles.business_name),active=1,updated_at=excluded.updated_at""",
                (str(provider_user_id), self._clean(business_name), now, now),
            )

    def add_item(self, provider_user_id: str, item_name: str, category: str | None = None,
                 default_price: float | None = None, price_basis: str | None = None,
                 source: str = "text") -> int | None:
        name = self._clean(item_name); norm = self._norm(name)
        if not norm:
            return None
        self.enable_provider(provider_user_id)
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO catering_catalog_items(
                       provider_user_id,item_name,normalized_name,category,default_price,price_basis,active,source,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,1,?,?,?)
                   ON CONFLICT(provider_user_id,normalized_name) DO UPDATE SET
                     item_name=excluded.item_name,category=COALESCE(excluded.category,catering_catalog_items.category),
                     default_price=COALESCE(excluded.default_price,catering_catalog_items.default_price),
                     price_basis=COALESCE(excluded.price_basis,catering_catalog_items.price_basis),
                     active=1,source=excluded.source,updated_at=excluded.updated_at""",
                (str(provider_user_id), name, norm, self._clean(category),
                 float(default_price) if default_price is not None else None,
                 self._clean(price_basis), str(source), now, now),
            )
            row = conn.execute(
                "SELECT id FROM catering_catalog_items WHERE provider_user_id=? AND normalized_name=?",
                (str(provider_user_id), norm),
            ).fetchone()
            return int(row["id"]) if row else None

    def add_items(self, provider_user_id: str, items: List[Dict[str, Any] | str], source: str = "text") -> int:
        count = 0
        for item in items or []:
            data = {"item_name": item} if isinstance(item, str) else dict(item)
            if self.add_item(provider_user_id, data.get("item_name") or data.get("name"),
                             category=data.get("category"), default_price=data.get("default_price") or data.get("price"),
                             price_basis=data.get("price_basis"), source=source) is not None:
                count += 1
        return count

    def list_items(self, provider_user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM catering_catalog_items WHERE provider_user_id=? AND active=1 ORDER BY item_name",
                (str(provider_user_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_active_providers(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT provider_user_id,business_name,updated_at FROM catering_profiles WHERE active=1 ORDER BY updated_at DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def find_matching_providers(self, requested_items: List[Dict[str, Any] | str], limit: int = 20) -> List[Dict[str, Any]]:
        wanted = []
        for item in requested_items or []:
            name = item if isinstance(item, str) else item.get("item_name") or item.get("name")
            norm = self._norm(name)
            if norm:
                wanted.append(norm)
        if not wanted:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT c.provider_user_id,c.item_name,c.normalized_name,p.business_name
                   FROM catering_catalog_items c JOIN catering_profiles p ON p.provider_user_id=c.provider_user_id
                   WHERE c.active=1 AND p.active=1"""
            ).fetchall()
        matched: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            hits = sum(1 for requested in wanted if self._similar(requested, str(row["normalized_name"])))
            if not hits:
                continue
            provider_id = str(row["provider_user_id"])
            entry = matched.setdefault(provider_id, {"provider_user_id": provider_id, "business_name": row["business_name"], "matched_items": set()})
            for requested in wanted:
                if self._similar(requested, str(row["normalized_name"])):
                    entry["matched_items"].add(requested)
        result = []
        for entry in matched.values():
            count = len(entry["matched_items"])
            result.append({"provider_user_id": entry["provider_user_id"], "business_name": entry["business_name"],
                           "matched_items": count, "requested_items": len(wanted),
                           "match_percent": round((count / len(wanted)) * 100, 1)})
        result.sort(key=lambda row: (-row["matched_items"], str(row["provider_user_id"])))
        return result[: max(1, int(limit))]

    def catalog_covers(self, provider_user_id: str, requested_name: str) -> bool:
        requested = self._norm(requested_name)
        return any(self._similar(requested, str(item["normalized_name"])) for item in self.list_items(provider_user_id))

    @staticmethod
    def _clean(value: Any) -> str | None:
        text = " ".join(str(value or "").strip().split())
        return text or None

    @staticmethod
    def _norm(value: Any) -> str:
        return " ".join(re.sub(r"[^\w\u0C00-\u0C7F\u0900-\u097F]+", " ", str(value or "").casefold()).split())

    @classmethod
    def _similar(cls, a: str, b: str) -> bool:
        if not a or not b:
            return False
        if a == b or a in b or b in a:
            return True
        at, bt = set(a.split()), set(b.split())
        return bool(at and bt and (len(at & bt) / max(1, min(len(at), len(bt)))) >= 0.6)
