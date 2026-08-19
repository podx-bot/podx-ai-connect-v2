"""Safe fresh-test reset wrapper for end-to-end WhatsApp validation.

The production user/deal history is preserved. A reset snapshots the current
profile/capabilities for diagnostics, pauses active deal/marketplace records,
clears current-role state used by matching, and resets the conversation session.
"""
from __future__ import annotations

import json


class FreshTestResetService:
    RESET_COMMANDS = {
        "fresh test",
        "start fresh",
        "reset test",
        "fresh start",
        "ఫ్రెష్ టెస్ట్",
        "కొత్తగా మొదలు",
        "కొత్తగా మొదలుపెట్టు",
    }

    GREETINGS = {"hi", "hello", "hey", "హాయ్", "హలో"}

    ACTIVE_DEAL_STATES = (
        "WAITING_SELLER_DETAILS",
        "WAITING_BUYER_CONFIRM",
        "WAITING_BUYER_CHANGE",
        "WAITING_SELLER_REVISION",
    )

    def __init__(self, delegate, user_repository=None, session_registry=None) -> None:
        self.delegate = delegate
        self.users = user_repository
        self.sessions = session_registry
        self._ensure_archive_schema()

    def process(self, sender_mobile: str, message: str) -> str:
        sender = str(sender_mobile)
        clean = str(message or "").strip()
        normalized = " ".join(clean.casefold().split())

        if normalized in self.RESET_COMMANDS:
            self._reset(sender)
            return (
                "✅ Fresh test mode ready. పాత profile/deal history delete కాలేదు; archive/pause చేశాను. "
                "ఇప్పుడు Hi పంపండి — PODX first-time profile onboarding నుంచి మొదలవుతుంది."
            )

        # A greeting must never be silently consumed by a stale deal state.
        if normalized in self.GREETINGS and self._has_active_deal(sender):
            return (
                "మీకు ఒక పాత active deal ఉంది. దాన్ని continue చేయాలంటే ‘Continue’ పంపండి. "
                "మొదటి నుంచి clean test చేయాలంటే ‘Fresh Test’ పంపండి."
            )

        return self.delegate.process(sender_mobile=sender, message=clean)

    def _database(self):
        return getattr(self.users, "database", None) if self.users is not None else None

    def _ensure_archive_schema(self) -> None:
        db = self._database()
        if db is None:
            return
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS fresh_test_archives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                whatsapp_mobile TEXT NOT NULL,
                user_json TEXT NOT NULL DEFAULT '{}',
                capabilities_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def _has_active_deal(self, sender: str) -> bool:
        db = self._database()
        if db is None:
            return False
        try:
            marks = ",".join("?" for _ in self.ACTIVE_DEAL_STATES)
            row = db.fetchone(
                f"""
                SELECT 1 FROM universal_deal_discussions
                WHERE (buyer_user_id=? OR seller_user_id=?)
                  AND status IN ({marks})
                LIMIT 1
                """,
                (sender, sender, *self.ACTIVE_DEAL_STATES),
            )
            return row is not None
        except Exception:
            return False

    def _reset(self, sender: str) -> None:
        db = self._database()
        if db is None:
            self._reset_session(sender)
            return

        user = self.users.find_by_whatsapp_mobile(sender) if self.users is not None else None
        capabilities = []
        if self.users is not None:
            try:
                capabilities = self.users.list_capabilities(sender)
            except Exception:
                capabilities = []

        # Snapshot first so Fresh Test never destroys historical profile context.
        db.execute(
            """
            INSERT INTO fresh_test_archives(whatsapp_mobile,user_json,capabilities_json)
            VALUES(?,?,?)
            """,
            (
                sender,
                json.dumps(user or {}, ensure_ascii=False, default=str),
                json.dumps(capabilities, ensure_ascii=False),
            ),
        )

        # Pause active state instead of deleting it. This keeps history available
        # while ensuring old records cannot leak into a clean test or active match.
        self._pause_active_deals(db, sender)
        self._pause_marketplace_profiles(db, sender)

        # Re-enter the normal onboarding contract with a clean current role/profile
        # surface. The archived snapshot above preserves the pre-test values.
        try:
            db.execute(
                """
                UPDATE users
                SET registration_complete=0,
                    role=NULL,
                    job_category=NULL,
                    experience=NULL,
                    availability=NULL,
                    worker_registration_complete=0,
                    latitude=NULL,
                    longitude=NULL,
                    location_name=NULL,
                    location_address=NULL,
                    location_updated_at=NULL,
                    updated_at=CURRENT_TIMESTAMP
                WHERE whatsapp_mobile=?
                """,
                (sender,),
            )
        except Exception:
            # Legacy/minimal schemas still need to re-enter onboarding safely.
            db.execute(
                """
                UPDATE users
                SET registration_complete=0, updated_at=CURRENT_TIMESTAMP
                WHERE whatsapp_mobile=?
                """,
                (sender,),
            )

        try:
            db.execute("DELETE FROM user_capabilities WHERE whatsapp_mobile=?", (sender,))
        except Exception:
            pass

        self._reset_session(sender)

    def _pause_active_deals(self, db, sender: str) -> None:
        try:
            marks = ",".join("?" for _ in self.ACTIVE_DEAL_STATES)
            db.execute(
                f"""
                UPDATE universal_deal_discussions
                SET status='PAUSED_FRESH_TEST', updated_at=CURRENT_TIMESTAMP
                WHERE (buyer_user_id=? OR seller_user_id=?)
                  AND status IN ({marks})
                """,
                (sender, sender, *self.ACTIVE_DEAL_STATES),
            )
        except Exception:
            pass

    @staticmethod
    def _pause_marketplace_profiles(db, sender: str) -> None:
        for sql in (
            """
            UPDATE seller_listings
            SET status='PAUSED_FRESH_TEST', updated_at=CURRENT_TIMESTAMP
            WHERE seller_mobile=? AND status='ACTIVE'
            """,
            """
            UPDATE service_provider_profiles
            SET status='PAUSED_FRESH_TEST', updated_at=CURRENT_TIMESTAMP
            WHERE provider_mobile=? AND status='ACTIVE'
            """,
        ):
            try:
                db.execute(sql, (sender,))
            except Exception:
                # Some deployments/tests may not have that optional vertical table.
                continue

    def _reset_session(self, sender: str) -> None:
        registry = self.sessions
        if registry is None:
            return
        for method_name in ("reset", "clear", "remove", "delete"):
            method = getattr(registry, method_name, None)
            if callable(method):
                try:
                    method(sender)
                    return
                except Exception:
                    continue
        # Common in-memory registry fallback.
        for attr in ("sessions", "_sessions", "registry", "_registry"):
            store = getattr(registry, attr, None)
            if isinstance(store, dict):
                store.pop(sender, None)
                return
