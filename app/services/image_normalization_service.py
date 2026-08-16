"""Bounded image normalization and lightweight visual fingerprinting for PODX media flows."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Optional

from PIL import Image, ImageOps


@dataclass(frozen=True)
class NormalizedImage:
    analysis_bytes: bytes
    analysis_mime_type: str
    preview_bytes: bytes
    preview_mime_type: str
    visual_signature: str
    original_width: int
    original_height: int
    analysis_width: int
    analysis_height: int


class ImageNormalizationService:
    """Normalize one downloaded image once for multimodal analysis and future previews."""

    def __init__(self, analysis_max_px: int = 1600, preview_max_px: int = 320, jpeg_quality: int = 84) -> None:
        self.analysis_max_px = max(256, int(analysis_max_px))
        self.preview_max_px = max(64, int(preview_max_px))
        self.jpeg_quality = max(55, min(int(jpeg_quality), 92))

    def normalize(self, image_bytes: bytes) -> Optional[NormalizedImage]:
        if not image_bytes:
            return None
        try:
            with Image.open(BytesIO(image_bytes)) as opened:
                image = ImageOps.exif_transpose(opened)
                original_width, original_height = image.size
                if original_width <= 0 or original_height <= 0:
                    return None
                image = image.convert("RGB")

                analysis = image.copy()
                analysis.thumbnail((self.analysis_max_px, self.analysis_max_px), Image.Resampling.LANCZOS)
                analysis_bytes = self._jpeg_bytes(analysis, self.jpeg_quality)

                preview = image.copy()
                preview.thumbnail((self.preview_max_px, self.preview_max_px), Image.Resampling.LANCZOS)
                preview_bytes = self._jpeg_bytes(preview, min(self.jpeg_quality, 78))

                signature = self._average_hash(image)
                return NormalizedImage(
                    analysis_bytes=analysis_bytes,
                    analysis_mime_type="image/jpeg",
                    preview_bytes=preview_bytes,
                    preview_mime_type="image/jpeg",
                    visual_signature=signature,
                    original_width=original_width,
                    original_height=original_height,
                    analysis_width=analysis.size[0],
                    analysis_height=analysis.size[1],
                )
        except Exception:
            return None

    @staticmethod
    def _jpeg_bytes(image: Image.Image, quality: int) -> bytes:
        out = BytesIO()
        image.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
        return out.getvalue()

    @staticmethod
    def _average_hash(image: Image.Image) -> str:
        tiny = image.convert("L").resize((8, 8), Image.Resampling.LANCZOS)
        values = list(tiny.getdata())
        average = sum(values) / max(len(values), 1)
        bits = 0
        for value in values:
            bits = (bits << 1) | int(value >= average)
        return f"{bits:016x}"
