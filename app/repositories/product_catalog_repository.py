"""Seller-confirmed product catalog, media and FAQ persistence."""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class ProductCatalogRepository:
    def __init__(self, db_path: str = "podx.db") -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS seller_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seller_user_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    brand TEXT,
                    variant TEXT,
                    quantity REAL,
                    unit TEXT,
                    price REAL,
                    currency TEXT DEFAULT 'INR',
                    stock_status TEXT NOT NULL DEFAULT 'UNKNOWN',
                    delivery_available INTEGER NOT NULL DEFAULT 0,
                    pickup_available INTEGER NOT NULL DEFAULT 1,
                    image_media_id TEXT,
                    video_media_id TEXT,
                    features_json TEXT NOT NULL DEFAULT '[]',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_seller_products_seller ON seller_products(seller_user_id, active);
                CREATE INDEX IF NOT EXISTS idx_seller_products_subject ON seller_products(subject, active);
                CREATE TABLE IF NOT EXISTS product_faq (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    question_key TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'SELLER_CONFIRMED',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(product_id, question_key)
                );
                """
            )

    def upsert_product(self, seller_user_id: str, subject: str, **fields: Any) -> int:
        now = self._now()
        seller = str(seller_user_id)
        name = " ".join(str(subject or "").strip().split())
        if not name:
            raise ValueError("subject required")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM seller_products WHERE seller_user_id=? AND lower(subject)=lower(?) AND active=1 ORDER BY id DESC LIMIT 1",
                (seller, name),
            ).fetchone()
            values = {
                "brand": fields.get("brand"), "variant": fields.get("variant"), "quantity": fields.get("quantity"),
                "unit": fields.get("unit"), "price": fields.get("price"), "currency": fields.get("currency") or "INR",
                "stock_status": str(fields.get("stock_status") or "UNKNOWN").upper(),
                "delivery_available": 1 if fields.get("delivery_available") else 0,
                "pickup_available": 0 if fields.get("pickup_available") is False else 1,
                "image_media_id": fields.get("image_media_id"), "video_media_id": fields.get("video_media_id"),
                "features_json": json.dumps(fields.get("features") or [], ensure_ascii=False),
            }
            if row:
                product_id = int(row["id"])
                conn.execute(
                    """UPDATE seller_products SET brand=?,variant=?,quantity=?,unit=?,price=?,currency=?,stock_status=?,delivery_available=?,pickup_available=?,image_media_id=COALESCE(?,image_media_id),video_media_id=COALESCE(?,video_media_id),features_json=?,updated_at=? WHERE id=?""",
                    (*values.values(), now, product_id),
                )
                return product_id
            cur = conn.execute(
                """INSERT INTO seller_products(seller_user_id,subject,brand,variant,quantity,unit,price,currency,stock_status,delivery_available,pickup_available,image_media_id,video_media_id,features_json,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)""",
                (seller, name, *values.values(), now, now),
            )
            return int(cur.lastrowid)

    def get(self, product_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM seller_products WHERE id=?", (int(product_id),)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["features"] = json.loads(data.pop("features_json") or "[]")
        return data

    def find_active(self, seller_user_id: str, subject: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM seller_products WHERE seller_user_id=? AND lower(subject)=lower(?) AND active=1 ORDER BY id DESC LIMIT 1",
                (str(seller_user_id), str(subject).strip()),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["features"] = json.loads(data.pop("features_json") or "[]")
        return data

    def save_faq(self, product_id: int, question_key: str, answer: str, source: str = "SELLER_CONFIRMED") -> None:
        now = self._now()
        key = " ".join(str(question_key or "").casefold().split())
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO product_faq(product_id,question_key,answer,source,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(product_id,question_key) DO UPDATE SET answer=excluded.answer,source=excluded.source,updated_at=excluded.updated_at""",
                (int(product_id), key, str(answer).strip(), str(source), now, now),
            )

    def get_faq(self, product_id: int, question_key: str) -> Optional[str]:
        key = " ".join(str(question_key or "").casefold().split())
        with self._connect() as conn:
            row = conn.execute("SELECT answer FROM product_faq WHERE product_id=? AND question_key=?", (int(product_id), key)).fetchone()
        return str(row["answer"]) if row else None
