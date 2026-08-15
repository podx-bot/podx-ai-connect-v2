"""Lightweight PODX RAG knowledge repository.

Stores trusted knowledge chunks with source metadata and freshness. Uses SQLite
for deployment safety. Retrieval starts with lexical matching; vector providers
can be plugged in later without changing callers.
"""
from __future__ import annotations
import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

class RagKnowledgeRepository:
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
                CREATE TABLE IF NOT EXISTS rag_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    namespace TEXT NOT NULL,
                    owner_user_id TEXT,
                    subject TEXT,
                    content TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_ref TEXT,
                    trust_level TEXT NOT NULL DEFAULT 'VERIFIED',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    valid_until TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_rag_namespace ON rag_knowledge(namespace, active);
                CREATE INDEX IF NOT EXISTS idx_rag_subject ON rag_knowledge(subject, active);
                """
            )

    def add(self, namespace: str, content: str, *, owner_user_id: str | None = None, subject: str | None = None, source_type: str = "PODX_CONFIRMED", source_ref: str | None = None, trust_level: str = "VERIFIED", metadata: Dict[str, Any] | None = None, valid_until: str | None = None) -> int:
        text = " ".join(str(content or "").strip().split())
        if not text:
            raise ValueError("content required")
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO rag_knowledge(namespace,owner_user_id,subject,content,source_type,source_ref,trust_level,metadata_json,valid_until,active,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,1,?,?)""",
                (str(namespace).upper(), owner_user_id, subject, text, str(source_type).upper(), source_ref, str(trust_level).upper(), json.dumps(metadata or {}, ensure_ascii=False), valid_until, now, now),
            )
            return int(cur.lastrowid)

    def retrieve(self, query: str, *, namespaces: List[str] | None = None, owner_user_id: str | None = None, subject: str | None = None, limit: int = 5) -> List[Dict[str, Any]]:
        terms = self._terms(query)
        if not terms:
            return []
        where = ["active=1"]
        params: List[Any] = []
        if namespaces:
            placeholders = ",".join("?" for _ in namespaces)
            where.append(f"namespace IN ({placeholders})")
            params.extend([str(x).upper() for x in namespaces])
        if owner_user_id is not None:
            where.append("(owner_user_id=? OR owner_user_id IS NULL)")
            params.append(str(owner_user_id))
        if subject:
            where.append("(subject IS NULL OR lower(subject)=lower(?))")
            params.append(str(subject).strip())
        sql = "SELECT * FROM rag_knowledge WHERE " + " AND ".join(where) + " ORDER BY id DESC LIMIT 200"
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        scored=[]
        now = datetime.now(timezone.utc)
        for row in rows:
            if row.get("valid_until"):
                try:
                    if datetime.fromisoformat(str(row["valid_until"]).replace("Z", "+00:00")) < now:
                        continue
                except ValueError:
                    pass
            hay=(str(row.get("subject") or "")+" "+str(row.get("content") or "")).casefold()
            hits=sum(1 for term in terms if term in hay)
            if hits==0:
                continue
            score=hits/max(1,len(terms))
            if row.get("trust_level")=="VERIFIED": score += 0.15
            if row.get("source_type") in {"SELLER_CONFIRMED","PODX_CONFIRMED","OFFICIAL"}: score += 0.15
            row["retrieval_score"]=round(score,4)
            try: row["metadata"]=json.loads(row.pop("metadata_json") or "{}")
            except Exception: row["metadata"]={}
            scored.append(row)
        scored.sort(key=lambda x:(-x["retrieval_score"],-int(x["id"])))
        return scored[:max(1,int(limit))]

    @staticmethod
    def _terms(text: str) -> List[str]:
        normalized = re.sub(r"[^\w\u0C00-\u0C7F\u0900-\u097F]+", " ", str(text or "").casefold(), flags=re.UNICODE)
        return [t for t in normalized.split() if len(t) >= 2][:12]
