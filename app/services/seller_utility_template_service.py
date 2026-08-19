"""Approved WhatsApp utility-template sender for seller re-engagement.

Meta template approval happens outside the application, so the template name and
language are configuration-driven rather than hard-coded.

Expected approved template contract:
- body variable {{1}}: PODX request summary
- body variable {{2}}: request id
- quick-reply button 0: Confirm
- quick-reply button 1: Decline
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
                "parameters": [
                    self._text_parameter(summary),
                    self._text_parameter(request_id),
                ],
            },
            {
                "type": "button",
                "sub_type": "quick_reply",
                "index": "0",
                "parameters": [{"type": "payload", "payload": f"UNIV_SELLER_CONFIRM:{request_id}"}],
            },
            {
                "type": "button",
                "sub_type": "quick_reply",
                "index": "1",
                "parameters": [{"type": "payload", "payload": f"UNIV_SELLER_DECLINE:{request_id}"}],
            },
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
