"""Multi-AI image understanding -> structured request -> matching flow."""
from __future__ import annotations

import base64
import json
import re
import time
from typing import Any, Dict, Optional

import httpx
from google import genai
from google.genai import types

from app.services.image_normalization_service import ImageNormalizationService


class UniversalImageService:
    NEED_WORDS = {
        "need", "want", "buy", "కావాలి", "కొనాలి", "కొంటాను", "వెతుకుతున్నాను",
        "chahiye", "lena hai", "kharidna", "వద్దు కాదు కావాలి",
    }
    OFFER_WORDS = {
        "sell", "selling", "have", "offer", "అమ్మాలి", "అమ్ముతాను", "నా దగ్గర ఉంది",
        "ఇస్తాను", "bechna", "bechunga", "available",
    }
    GEMINI_IMAGE_MODELS = ("gemini-3.6-flash", "gemini-3.5-flash")

    def __init__(
        self,
        api_key: str,
        model: str,
        pending_repository,
        live_capture_service,
        client: Any | None = None,
        openai_api_key: str = "",
        openai_model: str = "gpt-5",
        min_confidence: float = 0.65,
        http_client: Any | None = None,
        image_normalizer: ImageNormalizationService | None = None,
    ) -> None:
        self.pending = pending_repository
        self.live = live_capture_service
        self.client = client or (genai.Client(api_key=api_key) if api_key else None)
        self.openai_api_key = str(openai_api_key or "").strip()
        self.openai_model = str(openai_model or "gpt-5").strip()
        self.min_confidence = max(0.0, min(float(min_confidence or 0.65), 1.0))
        self.http = http_client or httpx.Client(timeout=20.0)
        self.image_normalizer = image_normalizer or ImageNormalizationService()

    def process_image(
        self,
        sender_mobile: str,
        image_bytes: bytes,
        mime_type: str | None,
        media_ref: str,
        caption: str | None = None,
    ) -> str:
        if not image_bytes:
            return "Image data రాలేదు. దయచేసి photo మళ్లీ పంపండి."

        normalized = None
        normalize_started = time.perf_counter()
        try:
            normalized = self.image_normalizer.normalize(image_bytes)
        finally:
            print(
                f"IMAGE LATENCY: id={media_ref or 'unknown'} stage=normalize "
                f"ms={round((time.perf_counter() - normalize_started) * 1000)} "
                f"success={bool(normalized)}",
                flush=True,
            )

        analysis_bytes = normalized.analysis_bytes if normalized else image_bytes
        analysis_mime = normalized.analysis_mime_type if normalized else (mime_type or "image/jpeg")

        ai_started = time.perf_counter()
        payload = self._analyze_multi_ai(
            image_bytes=analysis_bytes,
            mime_type=analysis_mime,
            caption=caption,
        )
        print(
            f"IMAGE LATENCY: id={media_ref or 'unknown'} stage=multimodal_analysis "
            f"ms={round((time.perf_counter() - ai_started) * 1000)} success={bool(payload)}",
            flush=True,
        )
        if payload is None:
            return "Photo అర్థం చేసుకోవడంలో సమస్య వచ్చింది. దయచేసి మళ్లీ పంపండి లేదా చిన్న caption పెట్టండి."

        subject = " ".join(str(payload.get("subject") or "").strip().split())
        if not subject:
            return "ఈ photoలో product/service స్పష్టంగా గుర్తించలేకపోయాను. మరో clear photo పంపండి."

        constraints = payload.get("constraints") if isinstance(payload.get("constraints"), list) else []
        constraints = [str(item).strip() for item in constraints if str(item).strip()]
        brand = self._text(payload.get("brand"))
        model = self._text(payload.get("model"))
        if brand:
            constraints.append(f"brand:{brand}")
        if model:
            constraints.append(f"model:{model}")
        if normalized and normalized.visual_signature:
            constraints.append(f"visual_signature:{normalized.visual_signature}")
            constraints.append(
                f"analysis_size:{normalized.analysis_width}x{normalized.analysis_height}"
            )
            constraints.append(f"preview_bytes:{len(normalized.preview_bytes)}")

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
            "location_required": not bool(self._text(payload.get("location_text"))),
            "constraints": constraints,
            "confidence": self._confidence(payload),
        }

        match_started = time.perf_counter()
        if side in {"NEED", "OFFER"}:
            reply = self.live.process_structured(
                sender_mobile,
                request,
                source="image",
                media_ref=media_ref,
            )
            print(
                f"IMAGE LATENCY: id={media_ref or 'unknown'} stage=match_route "
                f"ms={round((time.perf_counter() - match_started) * 1000)}",
                flush=True,
            )
            return reply or f"'{subject}' photo అర్థమైంది. మీ requirementను process చేయలేకపోయాను; textలో ఒకసారి చెప్పండి."

        self.pending.save(sender_mobile, media_ref, request)
        print(
            f"IMAGE LATENCY: id={media_ref or 'unknown'} stage=clarification_hold "
            f"ms={round((time.perf_counter() - match_started) * 1000)}",
            flush=True,
        )
        return f"📷 Photoలో '{subject}' అని అర్థమైంది. ఇది మీకు కావాలా, లేక మీరు అమ్మాలా/ఇవ్వాలా?"

    def _analyze_multi_ai(self, image_bytes: bytes, mime_type: str, caption: str | None) -> Optional[Dict[str, Any]]:
        prompt = self._prompt(caption)
        best: Optional[Dict[str, Any]] = None
        best_confidence = -1.0

        if self.client is not None:
            for model in self.GEMINI_IMAGE_MODELS:
                try:
                    payload = self._analyze_gemini(model, prompt, image_bytes, mime_type)
                    confidence = self._confidence(payload)
                    print(f"PODX IMAGE BRAIN: provider=gemini model={model} confidence={confidence:.2f} status=success", flush=True)
                    if confidence > best_confidence:
                        best, best_confidence = payload, confidence
                    if self._acceptable(payload):
                        return payload
                except Exception as error:
                    print(
                        f"PODX IMAGE BRAIN: provider=gemini model={model} status=failed "
                        f"error={type(error).__name__}: {error}",
                        flush=True,
                    )

        if self.openai_api_key:
            try:
                payload = self._analyze_openai(prompt, image_bytes, mime_type)
                confidence = self._confidence(payload)
                print(
                    f"PODX IMAGE BRAIN: provider=openai model={self.openai_model} "
                    f"confidence={confidence:.2f} status=success",
                    flush=True,
                )
                if confidence > best_confidence:
                    best, best_confidence = payload, confidence
                if self._acceptable(payload):
                    return payload
            except Exception as error:
                print(
                    f"PODX IMAGE BRAIN: provider=openai model={self.openai_model} status=failed "
                    f"error={type(error).__name__}: {error}",
                    flush=True,
                )

        if best and str(best.get("subject") or "").strip():
            print(f"PODX IMAGE BRAIN: status=best_effort confidence={best_confidence:.2f}", flush=True)
            return best
        return None

    def _analyze_gemini(self, model: str, prompt: str, image_bytes: bytes, mime_type: str) -> Dict[str, Any]:
        response = self.client.models.generate_content(
            model=model,
            contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime_type), prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return self._parse_json(str(getattr(response, "text", "") or ""))

    def _analyze_openai(self, prompt: str, image_bytes: bytes, mime_type: str) -> Dict[str, Any]:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime_type};base64,{encoded}"
        response = self.http.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {self.openai_api_key}", "Content-Type": "application/json"},
            json={
                "model": self.openai_model,
                "input": [{
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": data_url, "detail": "high"},
                    ],
                }],
            },
        )
        response.raise_for_status()
        return self._parse_json(self._openai_output_text(response.json()))

    def _acceptable(self, payload: Dict[str, Any]) -> bool:
        subject = str(payload.get("subject") or "").strip()
        return bool(subject) and self._confidence(payload) >= self.min_confidence

    @staticmethod
    def _openai_output_text(data: Dict[str, Any]) -> str:
        direct = data.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        chunks = []
        for item in data.get("output") or []:
            if not isinstance(item, dict):
                continue
            for content in item.get("content") or []:
                if isinstance(content, dict) and content.get("type") == "output_text" and content.get("text"):
                    chunks.append(str(content["text"]))
        return "\n".join(chunks).strip()

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
            "You are the PODX visual commerce brain. Analyze the attached photo or screenshot. "
            "Return exactly one JSON object and no markdown. Read visible labels, packaging text, brand, model and product name when possible. "
            "Identify the physical product/material/service/work subject. Use the most specific visible product name as subject. "
            "Use caption only to infer intent. If caption clearly means wants/buys/needs, side=NEED. "
            "If caption clearly means sells/has/offers/provides, side=OFFER. Otherwise side=UNKNOWN. "
            "Never invent price, quantity, brand, model, location or intent. Confidence should reflect certainty.\n"
            "Schema: {\"side\":\"NEED|OFFER|UNKNOWN\",\"domain\":\"PRODUCT|SERVICE|WORK|WORKERS|OTHER\","
            "\"subject\":\"short free-form name\",\"brand\":string|null,\"model\":string|null,"
            "\"quantity\":number|null,\"unit\":string|null,\"price\":number|null,\"currency\":string|null,"
            "\"when_text\":string|null,\"location_text\":string|null,\"constraints\":[string],\"confidence\":0..1}.\n"
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
    def _confidence(payload: Dict[str, Any]) -> float:
        try:
            return max(0.0, min(float(payload.get("confidence") or 0.0), 1.0))
        except (TypeError, ValueError):
            return 0.0

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
