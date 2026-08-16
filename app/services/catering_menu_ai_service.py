"""AI extraction for caterer menu photos/PDFs with one-time confirmation before save."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types


class CateringMenuAIService:
    MODELS = ("gemini-3.6-flash", "gemini-3.5-flash")

    def __init__(self, api_key: str, catalog_repository, pending_repository, client: Any | None = None) -> None:
        self.catalog = catalog_repository
        self.pending = pending_repository
        self.client = client or (genai.Client(api_key=api_key) if api_key else None)

    def process_text(self, sender_mobile: str, message: str) -> Optional[str]:
        clean = " ".join(str(message or "").casefold().strip().split())
        if clean in {"cmenu confirm", "menu confirm", "confirm menu"}:
            return self.confirm(sender_mobile)
        if clean in {"cmenu cancel", "menu cancel", "cancel menu"}:
            return self.cancel(sender_mobile)
        return None

    def process_media(
        self,
        sender_mobile: str,
        content: bytes,
        mime_type: str,
        media_ref: str,
        caption: str | None = None,
        filename: str | None = None,
    ) -> Optional[str]:
        if not content or self.client is None:
            return None
        if not self._is_caterer(sender_mobile) and not self._caption_requests_menu(caption):
            return None
        payload = self._analyze(content, mime_type, caption, filename)
        if not payload or not bool(payload.get("menu_detected")):
            return None
        items = self._clean_items(payload.get("items"))
        if not items:
            return None
        source_type = "pdf" if "pdf" in str(mime_type or "").casefold() else "image"
        self.pending.save(sender_mobile, items, media_ref=media_ref, source_type=source_type)
        preview = ", ".join(str(item["item_name"]) for item in items[:12])
        more = f" +{len(items)-12} more" if len(items) > 12 else ""
        return (
            f"🍽️ Menuలో {len(items)} item(s) గుర్తించాను: {preview}{more}.\n"
            "Catalogలో save చేయాలంటే CMENU CONFIRM పంపండి. వద్దంటే CMENU CANCEL పంపండి."
        )

    def confirm(self, provider_user_id: str) -> str:
        pending = self.pending.get(provider_user_id)
        if not pending or not pending.get("items"):
            return "Confirm చేయడానికి pending Catering Menu లేదు."
        items = pending["items"]
        count = self.catalog.add_items(provider_user_id, items, source=str(pending.get("source_type") or "ai_media"))
        self.pending.clear(provider_user_id)
        return f"✅ {count} menu item(s) మీ Catering Catalogలో save అయ్యాయి."

    def cancel(self, provider_user_id: str) -> str:
        pending = self.pending.get(provider_user_id)
        if not pending:
            return "Pending Catering Menu లేదు."
        self.pending.clear(provider_user_id)
        return "సరే. AI గుర్తించిన menu items save చేయలేదు."

    def _analyze(self, content: bytes, mime_type: str, caption: str | None, filename: str | None) -> Optional[Dict[str, Any]]:
        prompt = self._prompt(caption, filename)
        best = None
        best_confidence = -1.0
        for model in self.MODELS:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=[types.Part.from_bytes(data=content, mime_type=mime_type), prompt],
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                payload = self._parse_json(str(getattr(response, "text", "") or ""))
                confidence = self._confidence(payload)
                if confidence > best_confidence:
                    best, best_confidence = payload, confidence
                if bool(payload.get("menu_detected")) and payload.get("items") and confidence >= 0.65:
                    return payload
            except Exception as error:
                print(f"PODX CATERING MENU AI: model={model} failed={type(error).__name__}: {error}", flush=True)
        if best and bool(best.get("menu_detected")) and best.get("items") and best_confidence >= 0.45:
            return best
        return None

    def _is_caterer(self, provider_user_id: str) -> bool:
        try:
            with self.catalog._connect() as conn:
                row = conn.execute(
                    "SELECT 1 FROM catering_profiles WHERE provider_user_id=? AND active=1 LIMIT 1",
                    (str(provider_user_id),),
                ).fetchone()
            return row is not None
        except Exception:
            return False

    @staticmethod
    def _caption_requests_menu(caption: str | None) -> bool:
        text = str(caption or "").casefold()
        return any(word in text for word in ("cmenu", "menu", "మెను", "catering", "కేటరింగ్"))

    @classmethod
    def _clean_items(cls, raw: Any) -> List[Dict[str, Any]]:
        result = []
        seen = set()
        if not isinstance(raw, list):
            return result
        for entry in raw:
            data = {"name": entry} if isinstance(entry, str) else (dict(entry) if isinstance(entry, dict) else {})
            name = " ".join(str(data.get("item_name") or data.get("name") or "").strip().split())
            key = name.casefold()
            if not name or key in seen:
                continue
            seen.add(key)
            price = cls._number(data.get("price") or data.get("default_price"))
            result.append(
                {
                    "item_name": name,
                    "category": cls._text(data.get("category")),
                    "default_price": price,
                    "price_basis": cls._text(data.get("price_basis")),
                }
            )
        return result

    @staticmethod
    def _prompt(caption: str | None, filename: str | None) -> str:
        return (
            "You extract catering menus for PODX. Inspect this image or PDF. Return one JSON object only. "
            "Set menu_detected=true only when the media clearly contains a catering/restaurant/function menu, food list, "
            "catering service list, or price list. Extract every clearly visible item/service. Do not invent unreadable items. "
            "Keep item names short. Price is numeric or null. price_basis can be per_plate, per_person, per_kg, package, item, or null. "
            "Schema: {\"menu_detected\":true|false,\"items\":[{\"name\":string,\"category\":string|null,"
            "\"price\":number|null,\"price_basis\":string|null}],\"confidence\":0..1}. "
            f"Caption: {str(caption or '<none>')}. Filename: {str(filename or '<none>')}."
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
            return max(0.0, min(float(payload.get("confidence") or 0), 1.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None or value == "" or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = re.sub(r"[^0-9.\-]", "", str(value))
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None

    @staticmethod
    def _text(value: Any) -> str | None:
        text = " ".join(str(value or "").strip().split())
        return text or None
