"""Response command adapter that never reports false seller delivery success."""
from __future__ import annotations

from app.services.universal_commerce_response_command_service import UniversalCommerceResponseCommandService


class ReliableUniversalCommerceResponseCommandService(UniversalCommerceResponseCommandService):
    def _buyer_interest(self, buyer: str, request_id: int, seller: str) -> str:
        request = self.demands.get(request_id)
        if not request or str(request.get("status") or "").upper() != "ACTIVE":
            return "ఈ PODX match ఇప్పుడు activeలో లేదు."
        try:
            expected_buyer, expected_seller = self.notifications.resolve_roles(
                request,
                seller if str(request.get("side") or "").upper() == "NEED" else buyer,
            )
        except ValueError:
            return "ఈ match role details సరైనవి కావు."
        if str(expected_buyer) != str(buyer) or str(expected_seller) != str(seller):
            return "ఈ match మీకు సంబంధించినది కాదు."

        result = self.notifications.register_interest(request, buyer, seller)
        status = str(result.get("status") or "")
        if status == "WAITING_SELLER_CONFIRM":
            return "✅ మీ ఆసక్తి sellerకి పంపాను. Seller confirm చేసిన వెంటనే next options మీకు వస్తాయి."
        if status == "SELLER_NOTIFICATION_FAILED":
            return "⚠️ మీ ఆసక్తి save అయింది, కానీ sellerకి WhatsApp delivery పంపలేకపోయాను. PODX delivery retry/fallback అవసరం ఉంది."
        if status == "ROLE_MISMATCH":
            return "ఈ match role details సరైనవి కావు."
        return "✅ మీ ఆసక్తి save చేశాను."
