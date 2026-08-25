from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.routes.debug import _prepare_askodox_app_identity
from app.api.routes.in_app_deal import InterestDecisionRequest, interest_action

router = APIRouter(prefix="/deals", tags=["Deals"])


class UniversalDealCreateRequest(BaseModel):
    user_id: str
    raw_text: str = Field(min_length=1, max_length=4000)
    intent: str | None = None
    opposite_intent: str | None = None
    subject: str | None = None
    category: str | None = None
    quantity: float | None = None
    unit: str | None = None
    price: float | None = None
    price_basis: str | None = None
    quality: str | None = None
    variant: str | None = None
    size: str | None = None
    weight: str | None = None
    model: str | None = None
    availability: str | None = None
    fulfilment: str | None = None
    timing: str | None = None
    location: dict | None = None
    dynamic_fields: dict = Field(default_factory=dict)
    party_a: dict | None = None
    party_b: dict | None = None


class AcceptMatchRequest(BaseModel):
    match_id: str = Field(min_length=1)


def _app_user(value: str) -> str:
    user_id = str(value or "").strip()
    if not user_id.lower().startswith("app-"):
        raise HTTPException(status_code=400, detail="ASKODOX app user_id required")
    return user_id


def _latest_created_deal(container, user_id: str):
    return container.database.fetchone(
        """
        SELECT id,user_id,side,domain,subject,quantity,unit,price,currency,
               when_text,location_text,latitude,longitude,status,created_at
        FROM universal_need_offer_records
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (user_id,),
    )


@router.post("")
def create_deal(payload: UniversalDealCreateRequest, request: Request) -> dict:
    """Create a universal ASKODOX requirement through the existing V2 Deal Brain.

    The app sends its normalized deal object, but V2 still runs the original natural
    request through the same conversation/extraction/capture pipeline used by other
    channels. This prevents the Flutter client from becoming a second source of
    business rules.
    """
    container = request.app.state.container
    user_id = _app_user(payload.user_id)
    _prepare_askodox_app_identity(container, user_id)

    before = _latest_created_deal(container, user_id)
    before_id = int(before["id"]) if before else 0
    reply = container.conversation_service.process(
        sender_mobile=user_id,
        message=" ".join(payload.raw_text.strip().split()),
    )
    created = _latest_created_deal(container, user_id)
    if not created or int(created["id"]) <= before_id:
        raise HTTPException(
            status_code=422,
            detail="ASKODOX understood the message but the requirement is not ready to publish yet",
        )

    item = dict(created)
    deal_id = int(item["id"])
    return {
        "id": deal_id,
        "deal_id": deal_id,
        "request_id": deal_id,
        "contract_version": 1,
        "status": item.get("status"),
        "side": item.get("side"),
        "domain": item.get("domain"),
        "subject": item.get("subject"),
        "reply": reply,
    }


@router.get("/{deal_id}/matches")
def get_matches(deal_id: int, request: Request) -> dict:
    """Return genuine opposite-party responders for a published requirement.

    Only responders who actually expressed interest are returned. Targeted users who
    have not consented are intentionally not presented as connectable matches.
    """
    container = request.app.state.container
    demand = container.universal_demand_repository.get(deal_id)
    if not demand:
        raise HTTPException(status_code=404, detail="deal not found")

    rows = container.database.fetchall(
        """
        SELECT i.responder_user_id,i.qualification_status,i.responder_status,
               i.requester_status,i.created_at,
               n.distance_km,n.relevance_score
        FROM universal_interests i
        LEFT JOIN universal_notifications n
          ON n.request_id=i.request_id AND n.target_user_id=i.responder_user_id
        WHERE i.request_id=?
          AND i.responder_status='INTERESTED'
          AND i.requester_status='PENDING'
        ORDER BY COALESCE(n.relevance_score,0) DESC, i.id DESC
        LIMIT 100
        """,
        (deal_id,),
    )

    matches = []
    for row in rows:
        item = dict(row)
        responder = str(item.get("responder_user_id") or "")
        if not responder:
            continue
        score = item.get("relevance_score")
        if score is not None:
            score = float(score)
            if score > 1:
                score = score / 100.0
        matches.append(
            {
                "id": responder,
                "match_id": responder,
                "provider_id": responder,
                "title": "Interested match",
                "subtitle": str(item.get("qualification_status") or "Ready to connect"),
                "score": score,
                "distance_km": item.get("distance_km"),
                "price": None,
            }
        )

    return {
        "deal_id": deal_id,
        "request_id": deal_id,
        "contract_version": 1,
        "status": demand.get("status"),
        "match_count": len(matches),
        "matches": matches,
        "waiting_for_interest": len(matches) == 0,
    }


@router.post("/{deal_id}/accept-match")
def accept_match(deal_id: int, payload: AcceptMatchRequest, request: Request) -> dict:
    """Accept a responder who already opted in and open the existing in-app deal."""
    container = request.app.state.container
    demand = container.universal_demand_repository.get(deal_id)
    if not demand:
        raise HTTPException(status_code=404, detail="deal not found")
    requester = _app_user(str(demand.get("user_id") or ""))
    responder = _app_user(payload.match_id)

    result = interest_action(
        InterestDecisionRequest(
            user_id=requester,
            request_id=deal_id,
            responder_user_id=responder,
            action="ACCEPT",
        ),
        request,
    )
    return {
        **result,
        "deal_id": deal_id,
        "request_id": deal_id,
        "contract_version": 1,
        "match_id": responder,
    }
