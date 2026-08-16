"""Runtime bridge from a selected Grocery RFQ quote to a local dispatch task."""
from __future__ import annotations

import re
from typing import Optional


class GroceryOrderRuntimeService:
    def __init__(
        self,
        rfq_repository,
        order_repository,
        dispatch_repository,
        contact_resolver,
        user_repository=None,
        dispatch_runtime=None,
    ) -> None:
        self.rfqs = rfq_repository
        self.orders = order_repository
        self.dispatch = dispatch_repository
        self.contact_resolver = contact_resolver
        self.users = user_repository
        self.dispatch_runtime = dispatch_runtime

    def process(self, sender_user_id: str, message: str) -> Optional[str]:
        clean = " ".join(str(message or "").strip().split())
        if self.dispatch_runtime is not None:
            dispatch_reply = self.dispatch_runtime.process(sender_user_id, clean)
            if dispatch_reply is not None:
                return dispatch_reply
        lowered = clean.casefold()
        if lowered.startswith("gselect"):
            if not self._registered(sender_user_id):
                return None
            return self._select_quote(sender_user_id, clean)
        if lowered.startswith("gaddress"):
            if not self._registered(sender_user_id):
                return None
            return self._set_address(sender_user_id, clean)
        return None

    def _select_quote(self, buyer_user_id: str, message: str) -> str:
        match = re.match(r"^gselect\s+#?(\d+)\s+(\S+)$", message, flags=re.IGNORECASE)
        if not match:
            return "Format: GSELECT <RFQ ID> <SELLER ID>"
        rfq_id = int(match.group(1))
        seller_user_id = str(match.group(2))
        rfq = self.rfqs.get_rfq(rfq_id)
        if not rfq or str(rfq.get("buyer_user_id")) != str(buyer_user_id):
            return f"RFQ #{rfq_id} మీ open grocery request కాదు."
        quotes = self.rfqs.submitted_quotes(rfq_id)
        selected = next((row for row in quotes if str(row.get("seller_user_id")) == seller_user_id), None)
        if selected is None:
            return f"Seller {seller_user_id} నుంచి RFQ #{rfq_id}కి submitted quote లేదు."
        priced = [row for row in selected.get("items") or [] if int(row.get("available") or 0) == 1 and row.get("price") is not None]
        subtotal = sum(float(row.get("price") or 0) for row in priced)
        delivery_fee = float(selected.get("delivery_fee") or 0)
        total = subtotal + delivery_fee
        order_id = self.orders.create_from_quote(
            rfq_id=rfq_id,
            quote_id=int(selected["id"]),
            buyer_user_id=buyer_user_id,
            seller_user_id=seller_user_id,
            quote_total=total,
            quoted_delivery_fee=delivery_fee,
        )
        return (
            f"✅ Grocery Order #{order_id}కి Seller {seller_user_id} select అయ్యారు. Quote total ₹{total:.0f}.\n"
            f"Delivery కోసం address పంపండి: GADDRESS {order_id} <your full address>"
        )

    def _set_address(self, buyer_user_id: str, message: str) -> str:
        match = re.match(r"^gaddress\s+#?(\d+)\s+(.+)$", message, flags=re.IGNORECASE)
        if not match:
            return "Format: GADDRESS <ORDER ID> <FULL DELIVERY ADDRESS>"
        order_id = int(match.group(1))
        address = " ".join(match.group(2).split())
        order = self.orders.get(order_id)
        if not order or str(order.get("buyer_user_id")) != str(buyer_user_id):
            return f"Grocery Order #{order_id} మీ order కాదు."
        if order.get("dispatch_task_id"):
            return f"🚚 Grocery Order #{order_id} delivery task ఇప్పటికే create అయింది: #{order['dispatch_task_id']}."
        if not self.orders.set_delivery_address(order_id, buyer_user_id, address):
            return f"Grocery Order #{order_id} address update చేయలేకపోయాను. Current status: {order.get('status')}."

        seller = self.contact_resolver(str(order["seller_user_id"])) or {}
        pickup_text = str(seller.get("location_address") or seller.get("location_name") or seller.get("area") or seller.get("address") or f"Seller {order['seller_user_id']}")
        order_ref = f"GROCERY-{order_id}"
        try:
            task_id = self.dispatch.create_task(
                order_ref=order_ref,
                seller_user_id=str(order["seller_user_id"]),
                buyer_user_id=str(buyer_user_id),
                pickup_lat=seller.get("latitude"),
                pickup_lon=seller.get("longitude"),
                pickup_text=pickup_text,
                drop_text=address,
                fee=float(order.get("quoted_delivery_fee") or 0) or None,
            )
        except Exception:
            refreshed = self.orders.get(order_id) or {}
            if refreshed.get("dispatch_task_id"):
                return f"🚚 Delivery task #{refreshed['dispatch_task_id']} ఇప్పటికే readyగా ఉంది."
            raise
        self.orders.attach_dispatch(order_id, task_id)

        offered = 0
        if self.dispatch_runtime is not None:
            offer_result = self.dispatch_runtime.offer_task(task_id)
            offered = int(offer_result.get("offered") or 0)
        if offered:
            return (
                f"🚚 Grocery Order #{order_id} delivery handoff ready. Dispatch Task #{task_id} create అయింది.\n"
                f"{offered} nearby delivery partner(s)కి offer పంపాను. First accepterకి task assign అవుతుంది."
            )
        return (
            f"🚚 Grocery Order #{order_id} delivery handoff ready. Dispatch Task #{task_id} create అయింది.\n"
            "ప్రస్తుతం nearby delivery partner available కనిపించలేదు; task OPENగా ఉంది."
        )

    def _registered(self, user_id: str) -> bool:
        if self.users is None:
            return True
        user = self.users.find_by_whatsapp_mobile(str(user_id)) or {}
        return int(user.get("registration_complete") or 0) == 1
