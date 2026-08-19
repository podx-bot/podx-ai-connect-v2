import sqlite3

from app.services.fresh_test_reset_service import FreshTestResetService


class DB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE users(
                whatsapp_mobile TEXT PRIMARY KEY,
                name TEXT,
                registration_complete INTEGER NOT NULL DEFAULT 0,
                role TEXT,
                job_category TEXT,
                experience TEXT,
                availability TEXT,
                worker_registration_complete INTEGER NOT NULL DEFAULT 0,
                latitude REAL,
                longitude REAL,
                location_name TEXT,
                location_address TEXT,
                location_updated_at TEXT,
                updated_at TEXT
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE user_capabilities(
                whatsapp_mobile TEXT,
                capability TEXT
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE universal_deal_discussions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                buyer_user_id TEXT NOT NULL,
                seller_user_id TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE seller_listings(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_mobile TEXT NOT NULL,
                product_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                updated_at TEXT
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE service_provider_profiles(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_mobile TEXT NOT NULL,
                service_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                updated_at TEXT
            )
            """
        )
        self.conn.commit()

    def execute(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def fetchone(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()


class Users:
    def __init__(self, db):
        self.database = db

    def find_by_whatsapp_mobile(self, mobile):
        row = self.database.fetchone("SELECT * FROM users WHERE whatsapp_mobile=?", (mobile,))
        if not row:
            return None
        data = dict(row)
        data["capabilities"] = self.list_capabilities(mobile)
        return data

    def list_capabilities(self, mobile):
        rows = self.database.conn.execute(
            "SELECT capability FROM user_capabilities WHERE whatsapp_mobile=? ORDER BY capability",
            (mobile,),
        ).fetchall()
        return [row["capability"] for row in rows]


class Sessions:
    def __init__(self):
        self._sessions = {"u1": object()}


class Delegate:
    def __init__(self):
        self.calls = []

    def process(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return "delegate reply"


def seed(db):
    db.execute(
        """
        INSERT INTO users(
            whatsapp_mobile,name,registration_complete,role,job_category,
            experience,availability,worker_registration_complete,latitude,longitude,
            location_name,location_address
        ) VALUES('u1','Manu',1,'WORKER','Catering','1-2 Years','Tomorrow',1,16.4,80.6,'Vuyyuru','Main Road')
        """
    )
    db.execute(
        "INSERT INTO user_capabilities(whatsapp_mobile,capability) VALUES('u1','BUYER')"
    )
    db.execute(
        "INSERT INTO user_capabilities(whatsapp_mobile,capability) VALUES('u1','WORKER')"
    )
    db.execute(
        """
        INSERT INTO universal_deal_discussions(buyer_user_id,seller_user_id,status)
        VALUES('u1','s1','WAITING_BUYER_CONFIRM')
        """
    )
    db.execute(
        "INSERT INTO seller_listings(seller_mobile,product_name,status) VALUES('u1','Chicken','ACTIVE')"
    )
    db.execute(
        "INSERT INTO service_provider_profiles(provider_mobile,service_name,status) VALUES('u1','Electrician','ACTIVE')"
    )


def test_hi_with_stale_active_deal_offers_continue_or_fresh_test():
    db = DB()
    seed(db)
    delegate = Delegate()
    service = FreshTestResetService(delegate, Users(db), Sessions())

    reply = service.process("u1", "Hi")

    assert "Continue" in reply
    assert "Fresh Test" in reply
    assert delegate.calls == []


def test_fresh_test_archives_profile_pauses_deal_and_reenters_onboarding():
    db = DB()
    seed(db)
    sessions = Sessions()
    service = FreshTestResetService(Delegate(), Users(db), sessions)

    reply = service.process("u1", "Fresh Test")

    assert "Fresh test mode ready" in reply
    user = db.fetchone("SELECT * FROM users WHERE whatsapp_mobile='u1'")
    assert user["registration_complete"] == 0
    cap = db.fetchone("SELECT 1 FROM user_capabilities WHERE whatsapp_mobile='u1'")
    assert cap is None
    deal = db.fetchone("SELECT status FROM universal_deal_discussions WHERE buyer_user_id='u1'")
    assert deal["status"] == "PAUSED_FRESH_TEST"
    archive = db.fetchone("SELECT * FROM fresh_test_archives WHERE whatsapp_mobile='u1'")
    assert archive is not None
    assert "Catering" in archive["user_json"]
    assert "u1" not in sessions._sessions


def test_fresh_test_isolates_old_role_profile_and_marketplace_activity():
    db = DB()
    seed(db)
    service = FreshTestResetService(Delegate(), Users(db), Sessions())

    service.process("u1", "fresh test")

    user = db.fetchone("SELECT * FROM users WHERE whatsapp_mobile='u1'")
    assert user["role"] is None
    assert user["job_category"] is None
    assert user["experience"] is None
    assert user["availability"] is None
    assert user["worker_registration_complete"] == 0
    assert user["latitude"] is None
    assert user["longitude"] is None
    assert user["location_name"] is None
    assert user["location_address"] is None

    listing = db.fetchone("SELECT status FROM seller_listings WHERE seller_mobile='u1'")
    provider = db.fetchone("SELECT status FROM service_provider_profiles WHERE provider_mobile='u1'")
    assert listing["status"] == "PAUSED_FRESH_TEST"
    assert provider["status"] == "PAUSED_FRESH_TEST"


def test_history_is_not_deleted_by_fresh_test():
    db = DB()
    seed(db)
    service = FreshTestResetService(Delegate(), Users(db), Sessions())

    service.process("u1", "reset test")

    assert db.fetchone("SELECT id FROM universal_deal_discussions WHERE buyer_user_id='u1'") is not None
    assert db.fetchone("SELECT id FROM seller_listings WHERE seller_mobile='u1'") is not None
    assert db.fetchone("SELECT id FROM service_provider_profiles WHERE provider_mobile='u1'") is not None
    assert db.fetchone("SELECT id FROM fresh_test_archives WHERE whatsapp_mobile='u1'") is not None


def test_normal_message_passes_through_when_no_reset_or_stale_greeting():
    db = DB()
    delegate = Delegate()
    service = FreshTestResetService(delegate, Users(db), Sessions())

    assert service.process("u2", "AC repair కావాలి") == "delegate reply"
    assert delegate.calls == [("u2", "AC repair కావాలి")]
