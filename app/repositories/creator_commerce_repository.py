"""Persistent creator/influencer campaign, lead and conversion attribution."""
from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class CreatorCommerceRepository:
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
                CREATE TABLE IF NOT EXISTS creator_campaigns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seller_user_id TEXT NOT NULL,
                    creator_user_id TEXT NOT NULL,
                    product_id INTEGER NOT NULL,
                    promo_code TEXT NOT NULL UNIQUE,
                    commission_type TEXT NOT NULL DEFAULT 'NONE',
                    commission_value REAL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(seller_user_id, creator_user_id, product_id, status)
                );
                CREATE INDEX IF NOT EXISTS idx_creator_campaigns_creator ON creator_campaigns(creator_user_id, status);
                CREATE INDEX IF NOT EXISTS idx_creator_campaigns_product ON creator_campaigns(product_id, status);

                CREATE TABLE IF NOT EXISTS creator_leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id INTEGER NOT NULL,
                    buyer_user_id TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'WHATSAPP',
                    status TEXT NOT NULL DEFAULT 'LEAD',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(campaign_id, buyer_user_id)
                );

                CREATE TABLE IF NOT EXISTS creator_conversions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id INTEGER NOT NULL,
                    buyer_user_id TEXT NOT NULL,
                    seller_user_id TEXT NOT NULL,
                    order_ref TEXT,
                    sale_amount REAL,
                    commission_amount REAL,
                    status TEXT NOT NULL DEFAULT 'CONFIRMED',
                    created_at TEXT NOT NULL,
                    UNIQUE(campaign_id, buyer_user_id, order_ref)
                );
                """
            )

    def create_campaign(self, seller_user_id: str, creator_user_id: str, product_id: int,
                        commission_type: str = "NONE", commission_value: float | None = None) -> Dict[str, Any]:
        seller = str(seller_user_id); creator = str(creator_user_id); product = int(product_id)
        ctype = str(commission_type or "NONE").upper()
        if ctype not in {"NONE", "PERCENT", "FIXED"}:
            raise ValueError("invalid commission type")
        now = self._now()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM creator_campaigns WHERE seller_user_id=? AND creator_user_id=? AND product_id=? AND status='ACTIVE'",
                (seller, creator, product),
            ).fetchone()
            if existing:
                return dict(existing)
            for _ in range(10):
                code = "PODX-" + secrets.token_hex(3).upper()
                try:
                    cur = conn.execute(
                        """INSERT INTO creator_campaigns(seller_user_id,creator_user_id,product_id,promo_code,commission_type,commission_value,status,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,'ACTIVE',?,?)""",
                        (seller, creator, product, code, ctype, commission_value, now, now),
                    )
                    row = conn.execute("SELECT * FROM creator_campaigns WHERE id=?", (cur.lastrowid,)).fetchone()
                    return dict(row)
                except sqlite3.IntegrityError:
                    continue
        raise RuntimeError("unable to allocate promo code")

    def get_campaign_by_code(self, promo_code: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM creator_campaigns WHERE upper(promo_code)=upper(?) AND status='ACTIVE'",
                (str(promo_code).strip(),),
            ).fetchone()
        return dict(row) if row else None

    def add_lead(self, campaign_id: int, buyer_user_id: str, source: str = "WHATSAPP") -> Dict[str, Any]:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO creator_leads(campaign_id,buyer_user_id,source,status,created_at,updated_at)
                   VALUES(?,?,?,'LEAD',?,?)
                   ON CONFLICT(campaign_id,buyer_user_id) DO UPDATE SET updated_at=excluded.updated_at""",
                (int(campaign_id), str(buyer_user_id), str(source), now, now),
            )
            row = conn.execute(
                "SELECT * FROM creator_leads WHERE campaign_id=? AND buyer_user_id=?",
                (int(campaign_id), str(buyer_user_id)),
            ).fetchone()
        return dict(row)

    def record_conversion(self, campaign_id: int, buyer_user_id: str, seller_user_id: str,
                          order_ref: str | None, sale_amount: float | None) -> Dict[str, Any]:
        campaign = self.get_campaign(int(campaign_id))
        if not campaign:
            raise ValueError("campaign not found")
        commission = self._commission(campaign, sale_amount)
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO creator_conversions(campaign_id,buyer_user_id,seller_user_id,order_ref,sale_amount,commission_amount,status,created_at)
                   VALUES(?,?,?,?,?,?,'CONFIRMED',?)""",
                (int(campaign_id), str(buyer_user_id), str(seller_user_id), order_ref, sale_amount, commission, now),
            )
            conn.execute(
                "UPDATE creator_leads SET status='CONVERTED',updated_at=? WHERE campaign_id=? AND buyer_user_id=?",
                (now, int(campaign_id), str(buyer_user_id)),
            )
            row = conn.execute(
                "SELECT * FROM creator_conversions WHERE campaign_id=? AND buyer_user_id=? AND order_ref IS ? ORDER BY id DESC LIMIT 1",
                (int(campaign_id), str(buyer_user_id), order_ref),
            ).fetchone()
        return dict(row) if row else {}

    def get_campaign(self, campaign_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM creator_campaigns WHERE id=?", (int(campaign_id),)).fetchone()
        return dict(row) if row else None

    def campaigns_for_creator(self, creator_user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM creator_campaigns WHERE creator_user_id=? AND status='ACTIVE' ORDER BY id DESC",
                (str(creator_user_id),),
            ).fetchall()
        return [dict(r) for r in rows]

    def campaign_stats(self, campaign_id: int) -> Dict[str, Any]:
        with self._connect() as conn:
            leads = conn.execute("SELECT COUNT(*) c FROM creator_leads WHERE campaign_id=?", (int(campaign_id),)).fetchone()["c"]
            conv = conn.execute("SELECT COUNT(*) c, COALESCE(SUM(sale_amount),0) sales, COALESCE(SUM(commission_amount),0) commission FROM creator_conversions WHERE campaign_id=?", (int(campaign_id),)).fetchone()
        return {"leads": int(leads), "conversions": int(conv["c"]), "sales": float(conv["sales"]), "commission": float(conv["commission"])}

    @staticmethod
    def _commission(campaign: Dict[str, Any], sale_amount: float | None) -> float:
        ctype = str(campaign.get("commission_type") or "NONE").upper()
        value = float(campaign.get("commission_value") or 0)
        if ctype == "FIXED":
            return max(0.0, value)
        if ctype == "PERCENT" and sale_amount is not None:
            return max(0.0, float(sale_amount) * value / 100.0)
        return 0.0
