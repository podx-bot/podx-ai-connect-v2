"""Domain-neutral provider catalog for product, service, catering and event RFQs."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List


class UniversalCatalogRepository:
    VALID_TYPES = {"GROCERY", "CATERING", "PRODUCT", "SERVICE", "EVENT", "OTHER"}

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
                CREATE TABLE IF NOT EXISTS universal_catalog_providers(
                    provider_user_id TEXT NOT NULL,
                    catalog_type TEXT NOT NULL,
                    business_name TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    source TEXT NOT NULL DEFAULT 'UNIVERSAL',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(provider_user_id,catalog_type)
                );
                CREATE TABLE IF NOT EXISTS universal_catalog_items(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_user_id TEXT NOT NULL,
                    catalog_type TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    category TEXT,
                    price REAL,
                    price_basis TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    source TEXT NOT NULL DEFAULT 'UNIVERSAL',
                    source_ref TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(provider_user_id,catalog_type,normalized_name)
                );
                CREATE INDEX IF NOT EXISTS idx_ucatalog_type_item
                ON universal_catalog_items(catalog_type,normalized_name,active);
                CREATE INDEX IF NOT EXISTS idx_ucatalog_provider
                ON universal_catalog_items(provider_user_id,catalog_type,active);
                """
            )

    def enable_provider(self, provider_user_id: str, catalog_type: str,
                        business_name: str | None = None, source: str = "UNIVERSAL") -> None:
        kind = self._kind(catalog_type)
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO universal_catalog_providers(
                       provider_user_id,catalog_type,business_name,active,source,created_at,updated_at
                   ) VALUES(?,?,?,1,?,?,?)
                   ON CONFLICT(provider_user_id,catalog_type) DO UPDATE SET
                     business_name=COALESCE(excluded.business_name,universal_catalog_providers.business_name),
                     active=1,source=excluded.source,updated_at=excluded.updated_at""",
                (str(provider_user_id), kind, self._clean(business_name), str(source), now, now),
            )

    def upsert_item(self, provider_user_id: str, catalog_type: str, item_name: str,
                    category: str | None = None, price: float | None = None,
                    price_basis: str | None = None, source: str = "UNIVERSAL",
                    source_ref: str | None = None, business_name: str | None = None) -> int | None:
        kind = self._kind(catalog_type)
        name = self._clean(item_name)
        norm = self._norm(name)
        if not norm:
            return None
        self.enable_provider(provider_user_id, kind, business_name=business_name, source=source)
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO universal_catalog_items(
                       provider_user_id,catalog_type,item_name,normalized_name,category,price,price_basis,
                       active,source,source_ref,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,1,?,?,?,?)
                   ON CONFLICT(provider_user_id,catalog_type,normalized_name) DO UPDATE SET
                     item_name=excluded.item_name,category=COALESCE(excluded.category,universal_catalog_items.category),
                     price=COALESCE(excluded.price,universal_catalog_items.price),
                     price_basis=COALESCE(excluded.price_basis,universal_catalog_items.price_basis),
                     active=1,source=excluded.source,source_ref=COALESCE(excluded.source_ref,universal_catalog_items.source_ref),
                     updated_at=excluded.updated_at""",
                (str(provider_user_id), kind, name, norm, self._clean(category),
                 float(price) if price is not None else None, self._clean(price_basis),
                 str(source), self._clean(source_ref), now, now),
            )
            row = conn.execute(
                "SELECT id FROM universal_catalog_items WHERE provider_user_id=? AND catalog_type=? AND normalized_name=?",
                (str(provider_user_id), kind, norm),
            ).fetchone()
            return int(row["id"]) if row else None

    def list_items(self, provider_user_id: str, catalog_type: str | None = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM universal_catalog_items WHERE provider_user_id=? AND active=1"
        params: List[Any] = [str(provider_user_id)]
        if catalog_type:
            sql += " AND catalog_type=?"
            params.append(self._kind(catalog_type))
        sql += " ORDER BY catalog_type,item_name"
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def match_providers(self, catalog_type: str, requested_items: List[Dict[str, Any] | str],
                        limit: int = 30) -> List[Dict[str, Any]]:
        kind = self._kind(catalog_type)
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
                """SELECT i.provider_user_id,i.normalized_name,p.business_name
                   FROM universal_catalog_items i
                   JOIN universal_catalog_providers p
                     ON p.provider_user_id=i.provider_user_id AND p.catalog_type=i.catalog_type
                   WHERE i.catalog_type=? AND i.active=1 AND p.active=1""",
                (kind,),
            ).fetchall()
        matched: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            hits = [requested for requested in wanted if self._similar(requested, str(row["normalized_name"]))]
            if not hits:
                continue
            provider_id = str(row["provider_user_id"])
            entry = matched.setdefault(provider_id, {
                "provider_user_id": provider_id,
                "business_name": row["business_name"],
                "matched": set(),
            })
            entry["matched"].update(hits)
        result = []
        for entry in matched.values():
            count = len(entry["matched"])
            result.append({
                "provider_user_id": entry["provider_user_id"],
                "business_name": entry["business_name"],
                "matched_items": count,
                "requested_items": len(wanted),
                "match_percent": round((count / len(wanted)) * 100, 1),
            })
        result.sort(key=lambda row: (-row["matched_items"], str(row["provider_user_id"])))
        return result[:max(1, int(limit))]

    def import_legacy_catalogs(self) -> Dict[str, int]:
        """Idempotently mirror existing catering/product catalogs into the common catalog."""
        counts = {"CATERING": 0, "PRODUCT": 0}
        with self._connect() as conn:
            tables = {str(row["name"]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            catering = []
            products = []
            if "catering_catalog_items" in tables:
                catering = conn.execute(
                    """SELECT c.id,c.provider_user_id,c.item_name,c.category,c.default_price,c.price_basis,p.business_name
                       FROM catering_catalog_items c LEFT JOIN catering_profiles p ON p.provider_user_id=c.provider_user_id
                       WHERE c.active=1"""
                ).fetchall()
            if "seller_products" in tables:
                products = conn.execute(
                    "SELECT id,seller_user_id,subject,brand,variant,price,unit FROM seller_products WHERE active=1"
                ).fetchall()
        for row in catering:
            if self.upsert_item(row["provider_user_id"], "CATERING", row["item_name"], category=row["category"],
                                price=row["default_price"], price_basis=row["price_basis"], source="LEGACY_CATERING",
                                source_ref=f"catering:{row['id']}", business_name=row["business_name"]):
                counts["CATERING"] += 1
        for row in products:
            category = " ".join(x for x in [row["brand"], row["variant"]] if x) or None
            if self.upsert_item(row["seller_user_id"], "PRODUCT", row["subject"], category=category,
                                price=row["price"], price_basis=row["unit"], source="LEGACY_PRODUCT",
                                source_ref=f"product:{row['id']}"):
                counts["PRODUCT"] += 1
        return counts

    @classmethod
    def _kind(cls, value: Any) -> str:
        kind = str(value or "OTHER").strip().upper()
        return kind if kind in cls.VALID_TYPES else "OTHER"

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
