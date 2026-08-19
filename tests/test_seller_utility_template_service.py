import os

from app.services.seller_utility_template_service import SellerUtilityTemplateService


class FakeWhatsApp:
    def __init__(self):
        self.payloads = []

    @staticmethod
    def _mobile(value):
        return "".join(ch for ch in str(value) if ch.isdigit())

    def _send_with_retry(self, payload):
        self.payloads.append(payload)
        return {
            "success": True,
            "status": "SENT_TO_PROVIDER",
            "provider_message_id": "wamid.template.1",
        }


def test_template_sender_requires_config(monkeypatch):
    monkeypatch.delenv("PODX_SELLER_INTEREST_TEMPLATE_NAME", raising=False)
    service = SellerUtilityTemplateService(FakeWhatsApp())

    result = service.send_seller_interest(
        recipient_mobile="+91 90000 00000",
        summary="5 kg chicken request",
        request_id=42,
    )

    assert result["success"] is False
    assert result["status"] == "SELLER_UTILITY_TEMPLATE_NOT_CONFIGURED"


def test_template_sender_builds_approved_contract(monkeypatch):
    monkeypatch.setenv("PODX_SELLER_INTEREST_TEMPLATE_NAME", "podx_seller_interest")
    monkeypatch.setenv("PODX_SELLER_INTEREST_TEMPLATE_LANGUAGE", "en")
    whatsapp = FakeWhatsApp()
    service = SellerUtilityTemplateService(whatsapp)

    result = service.send_seller_interest(
        recipient_mobile="+91 90000 00000",
        summary="5 kg chicken request",
        request_id=42,
    )

    assert result["success"] is True
    payload = whatsapp.payloads[0]
    assert payload["type"] == "template"
    assert payload["to"] == "919000000000"
    assert payload["template"]["name"] == "podx_seller_interest"
    components = payload["template"]["components"]
    assert components[0]["parameters"][0]["text"] == "5 kg chicken request"
    assert components[0]["parameters"][1]["text"] == "42"
    assert components[1]["parameters"][0]["payload"] == "UNIV_SELLER_CONFIRM:42"
    assert components[2]["parameters"][0]["payload"] == "UNIV_SELLER_DECLINE:42"
