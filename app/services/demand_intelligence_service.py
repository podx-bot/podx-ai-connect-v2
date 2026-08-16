"""Aggregate repeated local NEED records into seller/provider opportunity signals."""
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any


class DemandIntelligenceService:
    def __init__(self, demand_repository, targeting_service, signal_repository, whatsapp_service, contact_resolver,
                 min_count: int = 2, alert_preferences=None) -> None:
        self.demands = demand_repository
        self.targeting = targeting_service
        self.signals = signal_repository
        self.whatsapp = whatsapp_service
        self.contact_resolver = contact_resolver
        self.min_count = max(2, int(min_count))
        self.alert_preferences = alert_preferences or self._auto_alert_preferences(demand_repository)
        self._scan_lock = threading.Lock()

    @staticmethod
    def _auto_alert_preferences(repository):
        try:
            db_path = str(getattr(repository, "db_path", "") or "")
            if not db_path:
                return None
            from app.repositories.proactive_alert_preference_repository import ProactiveAlertPreferenceRepository
            return ProactiveAlertPreferenceRepository(db_path)
        except Exception:
            return None

    def trigger_async(self) -> bool:
        if self._scan_lock.locked():
            return False
        thread = threading.Thread(target=self._safe_scan, daemon=True, name="podx-demand-intelligence")
        thread.start()
        return True

    def _safe_scan(self) -> None:
        if not self._scan_lock.acquire(blocking=False):
            return
        try:
            self.scan_and_notify()
        except Exception:
            return
        finally:
            self._scan_lock.release()

    def scan_and_notify(self, limit: int = 500) -> dict[str, Any]:
        rows = [r for r in self.demands.list_active(limit=limit) if str(r.get("side") or "").upper() == "NEED"]
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            domain = str(row.get("domain") or "OTHER").upper()
            subject = self._normalize(row.get("subject"))
            area = self._normalize(row.get("location_text"))
            if not subject or domain not in {"PRODUCT", "SERVICE", "WORKERS"}:
                continue
            grouped[(domain, subject, area)].append(row)

        emitted = []
        notified = 0
        for (domain, subject_key, area_key), requests in grouped.items():
            if len(requests) < self.min_count:
                continue
            newest = max(requests, key=lambda r: int(r.get("id") or 0))
            plan = self.targeting.build_plan(newest, already_contacted_user_ids=[], per_wave_limit=10)
            recipients = []
            for wave in plan.get("waves") or []:
                for target in wave.get("targets") or []:
                    user_id = str(target.get("user_id") or "")
                    if user_id and user_id not in recipients:
                        recipients.append(user_id)
            if self.alert_preferences is not None:
                recipients = [user_id for user_id in recipients if self.alert_preferences.is_enabled(user_id)]
            if not recipients:
                continue

            signal_key = f"{domain}|{subject_key}|{area_key}"
            if not self.signals.claim(signal_key, domain, subject_key, area_key, len(requests)):
                continue

            delivered_recipients = []
            for user_id in recipients:
                contact = self.contact_resolver(user_id) or {}
                mobile = str(contact.get("mobile") or user_id)
                self.whatsapp.send_text_message(mobile, self._message(newest, count=len(requests)))
                notified += 1
                delivered_recipients.append(user_id)
            emitted.append({
                "domain": domain,
                "subject": newest.get("subject"),
                "location": newest.get("location_text"),
                "count": len(requests),
                "recipients": delivered_recipients,
            })
        return {"status": "NOTIFIED" if notified else "NO_NEW_SIGNAL", "signals": emitted, "notified": notified}

    @staticmethod
    def _message(request: dict[str, Any], count: int) -> str:
        subject = str(request.get("subject") or "item/service")
        location = str(request.get("location_text") or "your area")
        domain = str(request.get("domain") or "").upper()
        action = "మీ దగ్గర ఉంటే PODXలో add/offer చేయండి." if domain == "PRODUCT" else "మీరు provide చేస్తే PODXలో offer చేయండి."
        return f"📈 PODX Local Demand\n{location} ప్రాంతంలో '{subject}' కోసం {count} active customer requests ఉన్నాయి.\n{action}"

    @staticmethod
    def _normalize(value: Any) -> str:
        return " ".join(str(value or "").casefold().strip().split())
