from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/debug", tags=["Debug"])


class SellerLimitsRequest(BaseModel):
    user_id: str
    request_id: int
    buyer_user_id: str
    asking_price: float = Field(gt=0)
    floor_price: float = Field(gt=0)
    currency: str = "INR"


class BuyerOfferRequest(BaseModel):
    user_id: str
    request_id: int
    seller_user_id: str
    amount: float = Field(gt=0)


class SellerDecisionRequest(BaseModel):
    user_id: str
    request_id: int
    buyer_user_id: str
    action: str
    amount: float | None = Field(default=None, gt=0)


def _app_user(value: str, field: str = "user_id") -> str:
    user_id = str(value or "").strip()
    if not user_id.lower().startswith("app-"):
        raise HTTPException(status_code=400, detail=f"ASKODOX app {field} required")
    return user_id


def _ensure_table(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS in_app_deal_negotiations(
            request_id INTEGER NOT NULL,
            buyer_user_id TEXT NOT NULL,
            seller_user_id TEXT NOT NULL,
            asking_price REAL NOT NULL,
            floor_price REAL NOT NULL,
            buyer_offer REAL,
            final_price REAL,
            currency TEXT NOT NULL DEFAULT 'INR',
            negotiation_status TEXT NOT NULL DEFAULT 'OPEN',
            last_offer_by TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(request_id,buyer_user_id,seller_user_id)
        )
        """
    )


def _accepted_participants(container, request_id: int, user_a: str, user_b: str):
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
    return buyer, seller


def _notify(db, request_id: int, buyer: str, seller: str, recipient: str, title: str, body: str) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS in_app_deal_notifications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            buyer_user_id TEXT NOT NULL,
            seller_user_id TEXT NOT NULL,
            recipient_user_id TEXT NOT NULL,
            source_message_id INTEGER,
            notification_type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            read_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        INSERT INTO in_app_deal_notifications(
            request_id,buyer_user_id,seller_user_id,recipient_user_id,
            notification_type,title,body
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (request_id, buyer, seller, recipient, "NEGOTIATION", title, body),
    )


def _set_confirmed(db, request_id: int, buyer: str, seller: str, actor: str) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS in_app_deal_threads(
            request_id INTEGER NOT NULL,
            buyer_user_id TEXT NOT NULL,
            seller_user_id TEXT NOT NULL,
            deal_status TEXT NOT NULL DEFAULT 'NEGOTIATING',
            status_updated_by TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(request_id,buyer_user_id,seller_user_id)
        )
        """
    )
    db.execute(
        """
        UPDATE in_app_deal_threads
        SET deal_status='CONFIRMED',status_updated_by=?,updated_at=CURRENT_TIMESTAMP
        WHERE request_id=? AND buyer_user_id=? AND seller_user_id=?
        """,
        (actor, request_id, buyer, seller),
    )


@router.post("/deal-negotiation/seller-limits")
def seller_limits(payload: SellerLimitsRequest, request: Request) -> dict:
    container = request.app.state.container
    seller = _app_user(payload.user_id)
    buyer_input = _app_user(payload.buyer_user_id, "buyer_user_id")
    buyer, actual_seller = _accepted_participants(container, payload.request_id, seller, buyer_input)
    if seller != actual_seller:
        raise HTTPException(status_code=403, detail="only the seller can set negotiation limits")
    if payload.floor_price > payload.asking_price:
        raise HTTPException(status_code=400, detail="floor_price cannot exceed asking_price")

    db = container.database
    _ensure_table(db)
    db.execute(
        """
        INSERT INTO in_app_deal_negotiations(
            request_id,buyer_user_id,seller_user_id,asking_price,floor_price,currency,
            negotiation_status,last_offer_by,updated_at
        ) VALUES(?,?,?,?,?,?,'OPEN',?,CURRENT_TIMESTAMP)
        ON CONFLICT(request_id,buyer_user_id,seller_user_id) DO UPDATE SET
            asking_price=excluded.asking_price,
            floor_price=excluded.floor_price,
            currency=excluded.currency,
            negotiation_status='OPEN',
            final_price=NULL,
            last_offer_by=excluded.last_offer_by,
            updated_at=CURRENT_TIMESTAMP
        """,
        (payload.request_id, buyer, seller, payload.asking_price, payload.floor_price,
         payload.currency.strip().upper() or "INR", seller),
    )
    return {
        "status": "OPEN",
        "request_id": payload.request_id,
        "asking_price": payload.asking_price,
        "floor_price": payload.floor_price,
        "currency": payload.currency.strip().upper() or "INR",
    }


@router.post("/deal-negotiation/buyer-offer")
def buyer_offer(payload: BuyerOfferRequest, request: Request) -> dict:
    container = request.app.state.container
    buyer_input = _app_user(payload.user_id)
    seller_input = _app_user(payload.seller_user_id, "seller_user_id")
    buyer, seller = _accepted_participants(container, payload.request_id, buyer_input, seller_input)
    if buyer_input != buyer:
        raise HTTPException(status_code=403, detail="only the buyer can make this offer")

    db = container.database
    _ensure_table(db)
    row = db.fetchone(
        """
        SELECT asking_price,floor_price,currency,negotiation_status
        FROM in_app_deal_negotiations
        WHERE request_id=? AND buyer_user_id=? AND seller_user_id=?
        """,
        (payload.request_id, buyer, seller),
    )
    if not row:
        raise HTTPException(status_code=409, detail="seller negotiation limits are not set")
    if str(row["negotiation_status"]).upper() == "AGREED":
        raise HTTPException(status_code=409, detail="final price is already agreed")

    asking = float(row["asking_price"])
    floor = float(row["floor_price"])
    amount = float(payload.amount)
    if amount >= asking:
        final_price = asking
        status = "AGREED"
    elif amount >= floor:
        final_price = amount
        status = "AGREED"
    else:
        final_price = None
        status = "SELLER_REVIEW"

    db.execute(
        """
        UPDATE in_app_deal_negotiations
        SET buyer_offer=?,final_price=?,negotiation_status=?,last_offer_by=?,updated_at=CURRENT_TIMESTAMP
        WHERE request_id=? AND buyer_user_id=? AND seller_user_id=?
        """,
        (amount, final_price, status, buyer, payload.request_id, buyer, seller),
    )

    if status == "AGREED":
        _set_confirmed(db, payload.request_id, buyer, seller, buyer)
        _notify(db, payload.request_id, buyer, seller, seller, "Price agreed", f"Final price agreed at {final_price:g} {row['currency']}.")
    else:
        _notify(db, payload.request_id, buyer, seller, seller, "Offer needs your decision", f"Buyer offered {amount:g} {row['currency']}, below your allowed floor.")

    return {
        "status": status,
        "request_id": payload.request_id,
        "buyer_offer": amount,
        "final_price": final_price,
        "currency": row["currency"],
        "seller_action_required": status == "SELLER_REVIEW",
    }


@router.post("/deal-negotiation/seller-decision")
def seller_decision(payload: SellerDecisionRequest, request: Request) -> dict:
    container = request.app.state.container
    seller_input = _app_user(payload.user_id)
    buyer_input = _app_user(payload.buyer_user_id, "buyer_user_id")
    buyer, seller = _accepted_participants(container, payload.request_id, seller_input, buyer_input)
    if seller_input != seller:
        raise HTTPException(status_code=403, detail="only the seller can decide an escalated offer")

    action = payload.action.strip().upper()
    if action not in {"ACCEPT", "COUNTER", "DECLINE"}:
        raise HTTPException(status_code=400, detail="action must be ACCEPT, COUNTER or DECLINE")

    db = container.database
    _ensure_table(db)
    row = db.fetchone(
        """
        SELECT asking_price,floor_price,buyer_offer,currency,negotiation_status
        FROM in_app_deal_negotiations
        WHERE request_id=? AND buyer_user_id=? AND seller_user_id=?
        """,
        (payload.request_id, buyer, seller),
    )
    if not row:
        raise HTTPException(status_code=404, detail="negotiation not found")
    if str(row["negotiation_status"]).upper() != "SELLER_REVIEW":
        raise HTTPException(status_code=409, detail="seller decision is not required")

    final_price = None
    counter_price = None
    if action == "ACCEPT":
        final_price = float(row["buyer_offer"])
        status = "AGREED"
        _set_confirmed(db, payload.request_id, buyer, seller, seller)
    elif action == "COUNTER":
        if payload.amount is None:
            raise HTTPException(status_code=400, detail="counter amount is required")
        counter_price = float(payload.amount)
        if counter_price < float(row["floor_price"]) or counter_price > float(row["asking_price"]):
            raise HTTPException(status_code=400, detail="counter amount must be within seller limits")
        status = "COUNTERED"
    else:
        status = "DECLINED"

    db.execute(
        """
        UPDATE in_app_deal_negotiations
        SET final_price=?,negotiation_status=?,last_offer_by=?,updated_at=CURRENT_TIMESTAMP
        WHERE request_id=? AND buyer_user_id=? AND seller_user_id=?
        """,
        (final_price, status, seller, payload.request_id, buyer, seller),
    )
    body = (
        f"Final price agreed at {final_price:g} {row['currency']}." if status == "AGREED"
        else f"Seller countered at {counter_price:g} {row['currency']}." if status == "COUNTERED"
        else "Seller declined the offer."
    )
    _notify(db, payload.request_id, buyer, seller, buyer, "Negotiation updated", body)
    return {
        "status": status,
        "request_id": payload.request_id,
        "final_price": final_price,
        "counter_price": counter_price,
        "currency": row["currency"],
    }


@router.get("/deal-negotiation/{request_id}/{user_id}/{other_user_id}")
def negotiation_state(request_id: int, user_id: str, other_user_id: str, request: Request) -> dict:
    container = request.app.state.container
    user = _app_user(user_id)
    other = _app_user(other_user_id, "other_user_id")
    buyer, seller = _accepted_participants(container, request_id, user, other)
    db = container.database
    _ensure_table(db)
    row = db.fetchone(
        """
        SELECT asking_price,floor_price,buyer_offer,final_price,currency,
               negotiation_status,last_offer_by,updated_at
        FROM in_app_deal_negotiations
        WHERE request_id=? AND buyer_user_id=? AND seller_user_id=?
        """,
        (request_id, buyer, seller),
    )
    if not row:
        return {"status": "NOT_STARTED", "request_id": request_id}
    return {"request_id": request_id, **dict(row)}
