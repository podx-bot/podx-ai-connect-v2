import sqlite3

from app.services.admin_monitoring_runtime_service import AdminMonitoringRuntimeService
from app.services.admin_monitoring_service import AdminMonitoringService


class Delegate:
    def process(self, sender_user_id, message):
        return f"delegate:{message}"


def seed(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
    CREATE TABLE conversation_observability(id INTEGER PRIMARY KEY AUTOINCREMENT,sender_user_id TEXT,message_preview TEXT,detected_domain TEXT,route_source TEXT,outcome TEXT,error_type TEXT,metadata_json TEXT,created_at TEXT);
    INSERT INTO conversation_observability(sender_user_id,message_preview,detected_domain,outcome,metadata_json,created_at) VALUES('u1','need thing','PRODUCT','UNRESOLVED','{}','now');
    INSERT INTO conversation_observability(sender_user_id,message_preview,detected_domain,outcome,error_type,metadata_json,created_at) VALUES('u2','ride broke','RIDE','ERROR','ValueError','{}','now');
    CREATE TABLE delivery_statuses(provider_message_id TEXT,recipient_mobile TEXT,status TEXT,error_message TEXT);
    INSERT INTO delivery_statuses VALUES('m1','900','failed','api error');
    CREATE TABLE driver_kyc_profiles(driver_user_id TEXT PRIMARY KEY,status TEXT,submitted_at TEXT,reviewed_at TEXT,reviewed_by TEXT,rejection_reason TEXT,created_at TEXT,updated_at TEXT);
    INSERT INTO driver_kyc_profiles VALUES('d1','SUBMITTED','now',NULL,NULL,NULL,'now','now');
    CREATE TABLE universal_rfqs(id INTEGER PRIMARY KEY,requester_user_id TEXT,rfq_type TEXT,title TEXT,status TEXT,created_at TEXT);
    INSERT INTO universal_rfqs VALUES(1,'b1','CATERING','Birthday','OPEN','now');
    CREATE TABLE rides(id INTEGER PRIMARY KEY,status TEXT);
    INSERT INTO rides VALUES(1,'OPEN');
    CREATE TABLE ride_bookings(id INTEGER PRIMARY KEY,status TEXT);
    INSERT INTO ride_bookings VALUES(1,'ACCEPTED');
    """)
    conn.commit(); conn.close()


def test_snapshot_and_queues(tmp_path):
    db = str(tmp_path / 'podx.db'); seed(db)
    service = AdminMonitoringService(db)
    snap = service.snapshot()
    assert snap['unresolved'] == 1
    assert snap['runtime_errors'] == 1
    assert snap['failed_deliveries'] == 1
    assert snap['kyc_submitted'] == 1
    assert snap['open_rfqs'] == 1
    assert snap['open_rides'] == 1
    assert snap['accepted_ride_bookings'] == 1
    assert service.unresolved()[0]['outcome'] == 'ERROR'
    assert service.failed_deliveries()[0]['recipient_mobile'] == '900'
    assert service.pending_kyc()[0]['driver_user_id'] == 'd1'
    assert service.open_rfqs()[0]['rfq_type'] == 'CATERING'


def test_admin_authorization_and_delegation(tmp_path):
    db = str(tmp_path / 'podx.db'); seed(db)
    runtime = AdminMonitoringRuntimeService(AdminMonitoringService(db), Delegate(), admin_mobile='999')
    assert runtime.process('111', 'hello') == 'delegate:hello'
    assert 'authorized' in runtime.process('111', 'ADMIN STATUS')
    status = runtime.process('999', 'ADMIN STATUS')
    assert 'Unresolved: 1' in status and 'Failed deliveries: 1' in status
    assert 'need thing' in runtime.process('999', 'ADMIN UNRESOLVED')
    assert 'd1' in runtime.process('999', 'ADMIN KYC')
    assert '900' in runtime.process('999', 'ADMIN DELIVERIES')
    assert '#1 CATERING' in runtime.process('999', 'ADMIN RFQS')
