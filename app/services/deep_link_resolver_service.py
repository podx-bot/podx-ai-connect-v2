from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.services.partner_registry_service import PartnerDefinition
from app.services.universal_revenue_router_service import RevenueRouteType


@dataclass(frozen=True)
class ResolvedDestination:
    partner_id: str
    url: str
    attribution_id: str
    route_type: RevenueRouteType


class DeepLinkResolverService:
    """Build partner destinations without influencing recommendation ranking.

    This service only transforms an already-selected partner route into a tracked
    destination. It does not decide which offer should win.
    """

    @staticmethod
    def _append_query(url: str, params: dict[str, str]) -> str:
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.update({key: value for key, value in params.items() if value})
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    def resolve(
        self,
        partner: PartnerDefinition,
        *,
        attribution_id: str,
        destination_url: str | None = None,
    ) -> ResolvedDestination | None:
        url = destination_url or partner.base_url
        if not url:
            return None

        params = {"podx_attribution_id": attribution_id}
        if partner.tracking_parameter and partner.tracking_value:
            params[partner.tracking_parameter] = partner.tracking_value

        return ResolvedDestination(
            partner_id=partner.partner_id,
            url=self._append_query(url, params),
            attribution_id=attribution_id,
            route_type=partner.route_type,
        )
