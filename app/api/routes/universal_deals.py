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
    action: str | None = None
    domain: str | None = None
    subject: str | None = None
    category: str | None = None
    entities: dict = Field(default_factory=dict)
    quantity: float | None = None
    unit: str | None = None
    price: float | None = None
    currency: str | None = None
    confidence: float | None = None
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


_COARSE_DOMAINS = {"PRODUCT", "SERVICE", "WORKERS", "JOB", "RIDE", "DELIVERY", "APPOINTMENT"}
_NEED_WORDS = {"NEED", "BUY", "WANT", "SEEK", "REQUEST", "FIND", "HIRE", "BOOK"}
_OFFER_WORDS = {"OFFER", "SELL", "PROVIDE", "SUPPLY", "AVAILABLE"}


def _app_user(value: str) -> str:
    user_id = str(value or "").strip()
    if not user_id.lower().startswith("app-"):
        raise HTTPException(status_code=400, detail="ASKODOX app user_id required")
    return user_id


def _semantic_tokens(*values: str | None) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        normalized = str(value or "").upper().replace("-", "_").replace(" ", "_")
        tokens.update(part for part in normalized.split("_") if part)
    return tokens


def _semantic_side(payload: UniversalDealCreateRequest) -> str | None:
    tokens = _semantic_tokens(payload.action, payload.intent, payload.opposite_intent)
    if tokens & _NEED_WORDS:
        return "NEED"
    if tokens & _OFFER_WORDS:
        return "OFFER"
    return None


def _semantic_domain(payload: UniversalDealCreateRequest) -> str | None:
    entities = payload.entities or {}
    explicit = str(payload.domain or entities.get("domain") or "").strip().upper()
    if explicit and explicit != "OTHER":
        return explicit
    category = str(payload.category or "").strip().upper()
    if category in _COARSE_DOMAINS:
        return category
    tokens = _semantic_tokens(payload.action, payload.intent, payload.opposite_intent)
    return next((domain for domain in _COARSE_DOMAINS if domain in tokens), None)


def _semantic_subject(payload: UniversalDealCreateRequest) -> str | None:
    entities = payload.entities or {}
    for value in (
        payload.subject,
        entities.get("subject"),
        entities.get("item"),
        entities.get("product"),
        entities.get("service"),
        entities.get("title"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    category = str(payload.category or "").strip()
    if category and category.upper() not in _COARSE_DOMAINS:
        return category
    return None


def _structured_deal_request(payload: UniversalDealCreateRequest) -> dict | None:
    side = _semantic_side(payload)
    domain = _semantic_domain(payload)
    subject = _semantic_subject(payload)
    if not side or not domain or not subject:
        return None

    entities = dict(payload.entities or {})
    constraints = dict(payload.dynamic_fields or {})
    for key, value in {
        "category": payload.category,
        "price_basis": payload.price_basis,
        "quality": payload.quality,
        "variant": payload.variant,
        "size": payload.size,
        "weight": payload.weight,
        "model": payload.model,
        "availability": payload.availability,
        "fulfilment": payload.fulfilment,
        "party_a": payload.party_a,
        "party_b": payload.party_b,
        "entities": entities or None,
    }.items():
        if value not in (None, "", {}, []):
            constraints[key] = value

    location = payload.location or {}
    latitude = location.get("latitude", location.get("lat"))
    longitude = location.get("longitude", location.get("lng", location.get("lon")))
    location_text = location.get("location_text") or location.get("name") or location.get("address") or location.get("label")

    confidence = 1.0 if payload.confidence is None else max(0.0, min(1.0, float(payload.confidence)))
    return {
        "side": side,
        "domain": domain,
        "subject": subject,
        "quantity": payload.quantity,
        "unit": payload.unit,
        "price": payload.price,
        "currency": payload.currency,
        "when_text": payload.timing,
        "latitude": latitude,
        "longitude": longitude,
        "location_text": location_text,
        "constraints": constraints,
        "confidence": confidence,
    }


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
    """Create an ASKODOX requirement from semantic app data when available.

    Complete semantic payloads go straight to the universal structured capture path,
    which owns persistence, matching, targeting and notifications. Raw-text parsing is
    retained only as a backward-compatible fallback for incomplete/legacy clients.
    """
    container = request.app.state.container
    user_id = _app_user(payload.user_id)
    _prepare_askodox_app_identity(container, user_id)

    before = _latest_created_deal(container, user_id)
    before_id = int(before["id"]) if before else 0
    structured = _structured_deal_request(payload)
    if structured is not None:
        reply = container.universal_live_capture_service.process_structured(
            sender_mobile=user_id,
            request=structured,
            source="app",
        )
    else:
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
