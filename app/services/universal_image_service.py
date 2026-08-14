"""Image -> visual understanding -> universal request -> matching flow."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from google import genai
from google.genai import types


class UniversalImageService:
    NEED_WORDS = {
        "need", "want", "buy", "కావాలి", "కొనాలి", "కొంటాను", "వెతుకుతున్నాను",
        "chahiye", "lena hai", "kharidna", "వద్దు కాదు కావాలి",
    }
    OFFER_WORDS = {
        "sell", "selling", "have", "offer", "అమ్మాలి", "అమ్ముతాను", "నా దగ్గర ఉంది",
        "ఇస్తాను", "bechna", "bechunga", "available",
    }
    # Image understanding is intentionally isolated from the shared voice model setting.
    # A voice model value may be valid for audio but unavailable for multimodal image calls.
    IMAGE_MODELS = ("gemini-2.5-flash", "gemini-2.0-flash")

    def __init__(self, api_key: str, model: str, pending_repository,
                 live_capture_service, client: Any | None = None) -> None:
        self.model = self.IMAGE_MODELS[0]
        self.pending = pending_repository
        self.live = live_capture_service
        self.client = client or (genai.Client(api_key=api_key) if api_key else None)

    def process_image(self, sender_mobile: str, image_bytes: bytes,
                      mime_type: str | None, media_ref: str,
                      caption: str | None = None) -> str:
        if self.client is None:
            return "ఈ imageని ఇప్పుడు AIతో analyze చేయలేకపోతున్నాను. కొద్దిసేపటికి మళ్లీ పంపండి."
        if not image_bytes:
            return "Image data రాలేదు. దయచేసి photo మళ్లీ పంపండి."

        prompt = self._prompt(caption)
        payload = None
        last_error = None
        for model in self.IMAGE_MODELS:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=[
                        prompt,
                        types.Part.from_bytes(
                            data=image_bytes,
                            mime_type=mime_type or "image/jpeg",
                        ),
                    ],
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                raw = str(getattr(response, "text", "") or "").strip()
                payload = self._parse_json(raw)
                print(f"PODX IMAGE AI SUCCESS: model={model}", flush=True)
                break
            except Exception as error:
                last_error = error
                print(
                    f"PODX IMAGE AI MODEL FAILED: model={model} "
                    f"error={type(error).__name__}: {error}",
                    flush=True,
                )

        if payload is None:
            return "Photo అర్థం చేసుకోవడంలో సమస్య వచ్చింది. దయచేసి మళ్లీ పంపండి లేదా చిన్న caption పెట్టండి."

        subject = " ".join(str(payload.get("subject") or "").strip().split())
        if not subject:
            return "ఈ photoలో product/service స్పష్టంగా గుర్తించలేకపోయాను. మరో clear photo పంపండి."

        side = str(payload.get("side") or "UNKNOWN").upper()
        request = {
            "side": side,
            "domain": str(payload.get("domain") or "PRODUCT").upper(),
            "subject": subject,
            "quantity": self._number(payload.get("quantity")),
            "unit": self._text(payload.get("unit")),
            "price": self._number(payload.get("price")),
            "currency": self._text(payload.get("currency")) or ("INR" if payload.get("price") is not None else None),
            "when_text": self._text(payload.get("when_text")),
            "location_text": self._text(payload.get("location_text")),
            "location_required": True,
            "constraints": payload.get("constraints") if isinstance(payload.get("constraints"), list) else [],
            "confidence": max(0.0, min(float(payload.get("confidence") or 0.0), 1.0)),
        }

        if side in {"NEED", "OFFER"}:
            reply = self.live.process_structured(sender_mobile, request, source="image", media_ref=media_ref)
            return reply or f"'{subject}' photo అర్థమైంది. మీ requirementను process చేయలేకపోయాను; textలో ఒకసారి చెప్పండి."

        self.pending.save(sender_mobile, media_ref, request)
        return f"📷 Photoలో '{subject}' అని అర్థమైంది. ఇది మీకు కావాలా, లేక మీరు అమ్మాలా/ఇవ్వాలా?"

    def process_text(self, sender_mobile: str, message: str) -> Optional[str]:
        pending = self.pending.get(sender_mobile)
        if not pending:
            return None
        side = self._side_from_text(message)
        if side is None:
            return None
        request = dict(pending.get("request") or {})
        request["side"] = side
        self.pending.clear(sender_mobile)
        reply = self.live.process_structured(
            sender_mobile=sender_mobile,
            request=request,
            source="image",
            media_ref=str(pending.get("media_ref") or ""),
        )
        return reply or "Photo requirementను save చేయలేకపోయాను. చిన్నగా textలో మళ్లీ చెప్పండి."

    @classmethod
    def _side_from_text(cls, message: str) -> Optional[str]:
        text = " ".join(str(message or "").casefold().strip().split())
        if not text:
            return None
        if any(word in text for word in cls.NEED_WORDS):
            return "NEED"
        if any(word in text for word in cls.OFFER_WORDS):
            return "OFFER"
        return None

    @staticmethod
    def _prompt(caption: str | None) -> str:
        cap = str(caption or "").strip()
        return (
            "You are PODX visual understanding. Analyze the attached photo/screenshot. "
            "Return exactly one JSON object, no markdown. Read visible product labels/text when possible and use them for the subject. "
            "Identify the physical product/material/service/work subject visible. "
            "Use caption to infer user intent. If caption clearly means wants/buys/needs, side=NEED. "
            "If caption clearly means sells/has/offers/provides, side=OFFER. If intent is not clear, side=UNKNOWN. "
            "Do not invent brand/model/price/quantity that is not visible or stated.\n"
            "Schema: {\"side\":\"NEED|OFFER|UNKNOWN\",\"domain\":\"PRODUCT|SERVICE|WORK|WORKERS|OTHER\","
            "\"subject\":\"short free-form name\",\"quantity\":number|null,\"unit\":string|null,"
            "\"price\":number|null,\"currency\":string|null,\"when_text\":string|null,"
            "\"location_text\":string|null,\"constraints\":[string],\"confidence\":0..1}.\n"
            f"Caption: {cap if cap else '<none>'}"
        )

    @staticmethod
    def _parse_json(raw: str) -> Dict[str, Any]:
        text = str(raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("no json")
            data = json.loads(text[start:end + 1])
        if not isinstance(data, dict):
            raise ValueError("invalid json")
        return data

    @staticmethod
    def _text(value: Any) -> Optional[str]:
        if value is None:
            return None
        value = " ".join(str(value).strip().split())
        return value or None

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        if value is None or value == "" or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = re.sub(r"[^0-9.\-]", "", str(value))
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
