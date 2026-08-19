"""Approved WhatsApp utility-template sender for seller re-engagement.

Meta template approval happens outside the application, so the template name and
language are configuration-driven rather than hard-coded.

Current approved/template-in-review contract used by PODX:
- body variable {{1}} only
- no template buttons required

The single variable carries the request summary, request id, and explicit
CONFIRM/DECLINE instruction. This keeps the Meta template compact while still
preserving exact deal context for the seller reply flow.
"""
from __future__ import annotations

import os


class SellerUtilityTemplateService:
    TEMPLATE_NAME_ENV = "PODX_SELLER_INTEREST_TEMPLATE_NAME"
    TEMPLATE_LANGUAGE_ENV = "PODX_SELLER_INTEREST_TEMPLATE_LANGUAGE"

    def __init__(self, whatsapp_service) -> None:
        self.whatsapp = whatsapp_service

    @property
    def template_name(self) -> str:
        return os.getenv(self.TEMPLATE_NAME_ENV, "").strip()

    @property
    def language_code(self) -> str:
        return os.getenv(self.TEMPLATE_LANGUAGE_ENV, "en").strip() or "en"

    def is_configured(self) -> bool:
        return bool(self.template_name)

    @staticmethod
    def _text_parameter(value) -> dict:
        return {"type": "text", "text": str(value or "-").strip()[:900]}

    @staticmethod
    def _compact_body(summary, request_id) -> str:
        clean_summary = str(summary or "New PODX customer request").strip()
        return (
            f"Request #{int(request_id)}: {clean_summary} "
            "Reply CONFIRM if you can help, or DECLINE if you cannot."
        )[:900]

    def send_seller_interest(self, *, recipient_mobile, summary, request_id) -> dict:
        name = self.template_name
        if not name:
            return {
                "success": False,
                "status": "SELLER_UTILITY_TEMPLATE_NOT_CONFIGURED",
                "required_env": self.TEMPLATE_NAME_ENV,
            }

        request_id = int(request_id)
        components = [
            {
                "type": "body",
                "parameters": [self._text_parameter(self._compact_body(summary, request_id))],
            }
        ]
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": self.whatsapp._mobile(recipient_mobile),
            "type": "template",
            "template": {
                "name": name,
                "language": {"code": self.language_code},
                "components": components,
            },
        }
        result = self.whatsapp._send_with_retry(payload)
        return {
            **result,
            "template_name": name,
            "template_language": self.language_code,
        }
