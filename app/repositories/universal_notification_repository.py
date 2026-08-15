"""Persistence for universal targeted notifications and lead conversion."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

class UniversalNotificationRepository:
    def __init__(self,db_path:str="podx.db")->None:self.db_path=db_path;self._ensure_schema()
    def _connect(self):
        c=sqlite3.connect(self.db_path);c.row_factory=sqlite3.Row;return c
    @staticmethod
    def _now()->str:return datetime.now(timezone.utc).isoformat()
    def _ensure_schema(self):
        with self._connect() as c:
            c.executescript("""CREATE TABLE IF NOT EXISTS universal_notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,request_id INTEGER NOT NULL,requester_user_id TEXT NOT NULL,target_user_id TEXT NOT NULL,wave INTEGER NOT NULL DEFAULT 1,distance_km REAL,relevance_score REAL,status TEXT NOT NULL DEFAULT 'PENDING',provider_message_id TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(request_id,target_user_id)); CREATE TABLE IF NOT EXISTS universal_interests(id INTEGER PRIMARY KEY AUTOINCREMENT,request_id INTEGER NOT NULL,requester_user_id TEXT NOT NULL,responder_user_id TEXT NOT NULL,responder_status TEXT NOT NULL DEFAULT 'INTERESTED',requester_status TEXT NOT NULL DEFAULT 'PENDING',contact_shared INTEGER NOT NULL DEFAULT 0,qualification_status TEXT NOT NULL DEFAULT 'NEW',delivery_address TEXT,converted_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(request_id,responder_user_id));""")
            cols={r['name'] for r in c.execute('PRAGMA table_info(universal_interests)')}
            for name,sql in [('qualification_status',"TEXT NOT NULL DEFAULT 'NEW'"),('delivery_address','TEXT'),('converted_at','TEXT')]:
                if name not in cols:c.execute(f'ALTER TABLE universal_interests ADD COLUMN {name} {sql}')
    def reserve_notification(self,request_id,requester_user_id,target_user_id,wave=1,distance_km=None,relevance_score=None):
        try:
            with self._connect() as c:
                x=c.execute("INSERT INTO universal_notifications(request_id,requester_user_id,target_user_id,wave,distance_km,relevance_score,status,created_at,updated_at) VALUES(?,?,?,?,?,?,'PENDING',?,?)",(request_id,str(requester_user_id),str(target_user_id),wave,distance_km,relevance_score,self._now(),self._now()));return x.lastrowid
        except sqlite3.IntegrityError:return None
    def mark_sent(self,i,provider_message_id=None):
        with self._connect() as c:c.execute("UPDATE universal_notifications SET status='SENT',provider_message_id=?,updated_at=? WHERE id=?",(provider_message_id,self._now(),i))
    def mark_failed(self,i):
        with self._connect() as c:c.execute("UPDATE universal_notifications SET status='FAILED',updated_at=? WHERE id=?",(self._now(),i))
    def contacted_user_ids(self,rid):
        with self._connect() as c:return [str(r['target_user_id']) for r in c.execute('SELECT target_user_id FROM universal_notifications WHERE request_id=?',(rid,))]
    def record_interest(self,rid,buyer,seller):
        now=self._now()
        with self._connect() as c:
            c.execute("INSERT INTO universal_interests(request_id,requester_user_id,responder_user_id,responder_status,requester_status,contact_shared,qualification_status,created_at,updated_at) VALUES(?,?,?,'INTERESTED','PENDING',0,'NEW',?,?) ON CONFLICT(request_id,responder_user_id) DO UPDATE SET requester_user_id=excluded.requester_user_id,responder_status='INTERESTED',requester_status='PENDING',qualification_status='NEW',delivery_address=NULL,converted_at=NULL,updated_at=excluded.updated_at",(rid,str(buyer),str(seller),now,now));return c.execute('SELECT id FROM universal_interests WHERE request_id=? AND responder_user_id=?',(rid,str(seller))).fetchone()['id']
    def set_seller_decision(self,rid,seller,accepted):
        with self._connect() as c:c.execute('UPDATE universal_interests SET requester_status=?,qualification_status=?,updated_at=? WHERE request_id=? AND responder_user_id=?',('ACCEPTED' if accepted else 'REJECTED','READY_FOR_BUYER' if accepted else 'DECLINED',self._now(),rid,str(seller)))
    def set_requester_consent(self,rid,responder_user_id,accepted):self.set_seller_decision(rid,responder_user_id,accepted)
    def mark_waiting_address(self,rid,seller):
        with self._connect() as c:c.execute("UPDATE universal_interests SET qualification_status='WAITING_ADDRESS',updated_at=? WHERE request_id=? AND responder_user_id=? AND requester_status='ACCEPTED'",(self._now(),rid,str(seller)))
    def save_delivery_address(self,rid,seller,address):
        with self._connect() as c:c.execute("UPDATE universal_interests SET delivery_address=?,qualification_status='WAITING_FINAL_CONFIRM',converted_at=NULL,updated_at=? WHERE request_id=? AND responder_user_id=? AND requester_status='ACCEPTED'",(str(address).strip(),self._now(),rid,str(seller)))
    def confirm_order(self,rid,seller):
        with self._connect() as c:c.execute("UPDATE universal_interests SET qualification_status='CONVERTED',converted_at=?,updated_at=? WHERE request_id=? AND responder_user_id=? AND requester_status='ACCEPTED' AND qualification_status='WAITING_FINAL_CONFIRM'",(self._now(),self._now(),rid,str(seller)))
    def cancel_order(self,rid,seller):
        with self._connect() as c:c.execute("UPDATE universal_interests SET qualification_status='CANCELLED',converted_at=NULL,updated_at=? WHERE request_id=? AND responder_user_id=?",(self._now(),rid,str(seller)))
    def mark_contact_shared(self,rid,seller):
        with self._connect() as c:c.execute('UPDATE universal_interests SET contact_shared=1,updated_at=? WHERE request_id=? AND responder_user_id=?',(self._now(),rid,str(seller)))
    def get_interest(self,rid,seller):
        with self._connect() as c:r=c.execute('SELECT * FROM universal_interests WHERE request_id=? AND responder_user_id=?',(rid,str(seller))).fetchone();return dict(r) if r else None
    def was_targeted(self,rid,target):
        with self._connect() as c:return c.execute("SELECT 1 FROM universal_notifications WHERE request_id=? AND target_user_id=? AND status='SENT' LIMIT 1",(rid,str(target))).fetchone() is not None
    def latest_sent_request_for_target(self,target):
        with self._connect() as c:r=c.execute("SELECT request_id,requester_user_id,target_user_id,created_at FROM universal_notifications WHERE target_user_id=? AND status='SENT' ORDER BY id DESC LIMIT 1",(str(target),)).fetchone();return dict(r) if r else None
    def _latest(self,where,args):
        with self._connect() as c:r=c.execute('SELECT * FROM universal_interests WHERE '+where+' ORDER BY id DESC LIMIT 1',args).fetchone();return dict(r) if r else None
    def latest_interest_for_buyer(self,b):return self._latest("requester_user_id=? AND responder_status='INTERESTED' AND qualification_status NOT IN ('DECLINED','CANCELLED')",(str(b),))
    def latest_pending_interest_for_seller(self,s):return self._latest("responder_user_id=? AND responder_status='INTERESTED' AND requester_status='PENDING' AND contact_shared=0",(str(s),))
    def latest_waiting_address_for_buyer(self,b):return self._latest("requester_user_id=? AND requester_status='ACCEPTED' AND qualification_status='WAITING_ADDRESS'",(str(b),))
    def latest_waiting_final_confirm_for_buyer(self,b):return self._latest("requester_user_id=? AND requester_status='ACCEPTED' AND qualification_status='WAITING_FINAL_CONFIRM'",(str(b),))
    def latest_ready_for_buyer(self,b):return self._latest("requester_user_id=? AND requester_status='ACCEPTED' AND qualification_status='READY_FOR_BUYER'",(str(b),))
    def latest_qualified_interest_for_buyer(self,b):return self._latest("requester_user_id=? AND requester_status='ACCEPTED' AND qualification_status='CONVERTED'",(str(b),))
    def latest_pending_interest_for_requester(self,x):return self.latest_pending_interest_for_seller(x)
    def latest_waiting_address_for_responder(self,x):return self.latest_waiting_address_for_buyer(x)
    def latest_qualified_interest_for_responder(self,x):return self.latest_qualified_interest_for_buyer(x)
