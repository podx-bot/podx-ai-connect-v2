"""Aggregate selected Event child RFQs into one final booking package."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List


class EventBookingService:
    def __init__(self, rfq_repository, whatsapp_service, contact_resolver) -> None:
        self.rfqs = rfq_repository
        self.whatsapp = whatsapp_service
        self.contact_resolver = contact_resolver

    def package_summary(self, master_rfq_id: int, requester_user_id: str) -> Dict[str, Any]:
        master = self.rfqs.get_rfq(master_rfq_id)
        if not master or str(master.get("rfq_type") or "").upper() != "EVENT":
            return {"status": "MASTER_NOT_FOUND"}
        if str(master.get("requester_user_id") or "") != str(requester_user_id):
            return {"status": "NOT_OWNER"}
        children = self._children(master_rfq_id)
        selected: List[Dict[str, Any]] = []
        missing: List[str] = []
        total = 0.0
        for child in children:
            service = str((child.get("metadata") or {}).get("service_type") or child.get("title") or "Service")
            quote_id = child.get("selected_quote_id")
            if not quote_id or str(child.get("status") or "").upper() not in {"SELECTED", "BOOKED"}:
                missing.append(service)
                continue
            quote = self._quote(int(quote_id))
            if not quote:
                missing.append(service)
                continue
            amount = float(quote.get("provider_total") or 0)
            if quote.get("provider_total") is None:
                amount = float(quote.get("service_fee") or 0) + float(quote.get("delivery_fee") or 0)
            total += amount
            selected.append({
                "service": service,
                "rfq_id": int(child["id"]),
                "quote_id": int(quote["id"]),
                "provider_user_id": str(quote["provider_user_id"]),
                "total": round(amount, 2),
            })
        return {
            "status": "OK",
            "master": master,
            "selected": selected,
            "missing": missing,
            "combined_total": round(total, 2),
            "ready_to_book": bool(selected) and not missing,
        }

    def confirm_booking(self, master_rfq_id: int, requester_user_id: str) -> Dict[str, Any]:
        summary = self.package_summary(master_rfq_id, requester_user_id)
        if summary.get("status") != "OK":
            return summary
        if summary.get("missing"):
            return {**summary, "status": "INCOMPLETE_SELECTION"}
        master = summary["master"]
        if str(master.get("status") or "").upper() == "BOOKED":
            return {**summary, "status": "ALREADY_BOOKED"}
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            for row in summary["selected"]:
                conn.execute(
                    "UPDATE universal_rfqs SET status='BOOKED',updated_at=? WHERE id=? AND selected_quote_id=?",
                    (now, int(row["rfq_id"]), int(row["quote_id"])),
                )
            conn.execute(
                "UPDATE universal_rfqs SET status='BOOKED',updated_at=? WHERE id=? AND requester_user_id=?",
                (now, int(master_rfq_id), str(requester_user_id)),
            )
        for row in summary["selected"]:
            provider = self.contact_resolver(row["provider_user_id"]) or {}
            self.whatsapp.send_text_message(
                str(provider.get("mobile") or row["provider_user_id"]),
                f"✅ PODX Event Booking Confirmed\n"
                f"Master Event RFQ #{master_rfq_id}\n"
                f"Service: {row['service']}\n"
                f"Selected Quote: #{row['quote_id']}\n"
                f"Amount: ₹{row['total']:.0f}\n"
                f"Event: {master.get('title') or 'Function'}\n"
                f"Date: {master.get('event_date') or '-'}\n"
                f"Location: {master.get('location_text') or '-'}",
            )
        return {**summary, "status": "BOOKED"}

    def _children(self, master_rfq_id: int) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM universal_rfqs WHERE json_extract(metadata_json,'$.master_event_rfq_id')=? ORDER BY id",
                (int(master_rfq_id),),
            ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["metadata"] = self.rfqs._json(data.pop("metadata_json", None))
            result.append(data)
        return result

    def _quote(self, quote_id: int) -> Dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM universal_rfq_quotes WHERE id=?", (int(quote_id),)).fetchone()
        return dict(row) if row else None

    def _connect(self):
        conn = sqlite3.connect(self.rfqs.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn
