from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/debug", tags=["Debug"])


class InterestDecisionRequest(BaseModel):
    user_id: str
    request_id: int
    responder_user_id: str
    action: str


class DealMessageRequest(BaseModel):
    user_id: str
    request_id: int
    other_user_id: str
    message: str = Field(min_length=1, max_length=2000)


def _app_user(value: str, field: str = "user_id") -> str:
    user_id = str(value or "").strip()
    if not user_id.lower().startswith("app-"):
        raise HTTPException(status_code=400, detail=f"ASKODOX app {field} required")
    return user_id


def _ensure_messages_table(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS in_app_deal_messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            buyer_user_id TEXT NOT NULL,
            seller_user_id TEXT NOT NULL,
            sender_user_id TEXT NOT NULL,
            message_text TEXT NOT NULL,
            message_type TEXT NOT NULL DEFAULT 'USER',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_in_app_deal_messages_thread
        ON in_app_deal_messages(request_id,buyer_user_id,seller_user_id,id)
        """
    )


def _accepted_interest(container, request_id: int, user_a: str, user_b: str):
    demand = container.universal_demand_repository.get(request_id)
    if not demand:
        raise HTTPException(status_code=404, detail="request not found")
    buyer = str(demand.get("user_id") or "")
    if buyer not in {user_a, user_b}:
        raise HTTPException(status_code=403, detail="user is not a participant in this deal")
    seller = user_b if user_a == buyer else user_a
    interest = container.universal_notification_repository.get_interest(request_id, seller)
    if not interest or str(interest.get("requester_user_id") or "") != buyer:
        raise HTTPException(status_code=404, detail="deal interest not found")
    if str(interest.get("requester_status") or "").upper() != "ACCEPTED":
        raise HTTPException(status_code=409, detail="deal is not accepted yet")
    return demand, interest, buyer, seller


@router.post("/interest-action")
def interest_action(payload: InterestDecisionRequest, request: Request) -> dict:
    """Requester accepts or declines a seller's in-app interest card."""
    container = request.app.state.container
    requester = _app_user(payload.user_id)
    responder = _app_user(payload.responder_user_id, "responder_user_id")
    action = payload.action.strip().upper()
    if action not in {"ACCEPT", "DECLINE"}:
        raise HTTPException(status_code=400, detail="action must be ACCEPT or DECLINE")

    demand = container.universal_demand_repository.get(payload.request_id)
    if not demand or str(demand.get("status") or "").upper() != "ACTIVE":
        raise HTTPException(status_code=404, detail="active request not found")
    if str(demand.get("user_id") or "") != requester:
        raise HTTPException(status_code=403, detail="only the request owner can decide this interest")

    interest = container.universal_notification_repository.get_interest(payload.request_id, responder)
    if not interest or str(interest.get("requester_user_id") or "") != requester:
        raise HTTPException(status_code=404, detail="interest not found")
    if str(interest.get("requester_status") or "").upper() != "PENDING":
        raise HTTPException(status_code=409, detail="interest already decided")

    accepted = action == "ACCEPT"
    result = container.universal_notification_service.confirm_lead(
        demand,
        requester,
        responder,
        accepted,
    )

    if accepted and str(result.get("status") or "") == "IN_APP_READY_FOR_BUYER":
        _ensure_messages_table(container.database)
        container.database.execute(
            """
            INSERT INTO in_app_deal_messages(
                request_id,buyer_user_id,seller_user_id,sender_user_id,message_text,message_type
            ) VALUES(?,?,?,?,?,'SYSTEM')
            """,
            (
                payload.request_id,
                requester,
                responder,
                "system",
                "Deal accepted. You can continue this conversation inside ASKODOX.",
            ),
        )
        return {
            **result,
            "action": action,
            "conversation_ready": True,
            "thread": {
                "request_id": payload.request_id,
                "buyer_user_id": requester,
                "seller_user_id": responder,
            },
        }

    return {**result, "action": action, "conversation_ready": False}


@router.post("/deal-message")
def deal_message(payload: DealMessageRequest, request: Request) -> dict:
    """Send one message inside an accepted ASKODOX buyer/seller deal thread."""
    container = request.app.state.container
    sender = _app_user(payload.user_id)
    other = _app_user(payload.other_user_id, "other_user_id")
    _demand, _interest, buyer, seller = _accepted_interest(
        container, payload.request_id, sender, other
    )
    body = " ".join(payload.message.strip().split())
    if not body:
        raise HTTPException(status_code=400, detail="message is required")

    _ensure_messages_table(container.database)
    cursor = container.database.execute(
        """
        INSERT INTO in_app_deal_messages(
            request_id,buyer_user_id,seller_user_id,sender_user_id,message_text,message_type
        ) VALUES(?,?,?,?,?,'USER')
        """,
        (payload.request_id, buyer, seller, sender, body),
    )
    return {
        "status": "SENT",
        "channel": "in_app",
        "message_id": int(cursor.lastrowid),
        "request_id": payload.request_id,
        "sender_user_id": sender,
        "recipient_user_id": other,
        "message": body,
    }


@router.get("/deal-thread/{request_id}/{user_id}/{other_user_id}")
def deal_thread(request_id: int, user_id: str, other_user_id: str, request: Request) -> dict:
    """Read the accepted ASKODOX deal conversation for either participant."""
    container = request.app.state.container
    viewer = _app_user(user_id)
    other = _app_user(other_user_id, "other_user_id")
    demand, interest, buyer, seller = _accepted_interest(container, request_id, viewer, other)
    _ensure_messages_table(container.database)
    rows = container.database.fetchall(
        """
        SELECT id,sender_user_id,message_text,message_type,created_at
        FROM in_app_deal_messages
        WHERE request_id=? AND buyer_user_id=? AND seller_user_id=?
        ORDER BY id ASC
        LIMIT 200
        """,
        (request_id, buyer, seller),
    )
    return {
        "status": "OPEN",
        "channel": "in_app",
        "request_id": request_id,
        "viewer_user_id": viewer,
        "other_user_id": other,
        "deal": {
            "subject": demand.get("subject"),
            "quantity": demand.get("quantity"),
            "unit": demand.get("unit"),
            "price": demand.get("price"),
            "currency": demand.get("currency"),
            "qualification_status": interest.get("qualification_status"),
        },
        "messages": [dict(row) for row in rows],
    }
