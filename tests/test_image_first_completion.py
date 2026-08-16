from io import BytesIO

from PIL import Image

from app.services.image_normalization_service import ImageNormalizationService
from app.services.universal_matcher import UniversalMatcher


def _jpeg(width=2400, height=1200):
    image = Image.new("RGB", (width, height), (120, 80, 40))
    out = BytesIO()
    image.save(out, format="JPEG", quality=95)
    return out.getvalue()


def test_image_normalization_bounds_analysis_and_creates_preview_and_signature():
    result = ImageNormalizationService(analysis_max_px=1200, preview_max_px=240).normalize(_jpeg())

    assert result is not None
    assert max(result.analysis_width, result.analysis_height) <= 1200
    assert len(result.analysis_bytes) > 0
    assert len(result.preview_bytes) > 0
    assert result.analysis_mime_type == "image/jpeg"
    assert result.preview_mime_type == "image/jpeg"
    assert len(result.visual_signature) == 16


def test_visual_similarity_hook_rewards_matching_signatures_without_replacing_semantics():
    matcher = UniversalMatcher(repository=None)
    base = {
        "side": "NEED",
        "domain": "PRODUCT",
        "subject": "water pump",
        "latitude": 16.5,
        "longitude": 80.6,
        "constraints": ["visual_signature:ffffffffffffffff"],
    }
    same = {
        "side": "OFFER",
        "domain": "PRODUCT",
        "subject": "water pump",
        "latitude": 16.5,
        "longitude": 80.6,
        "constraints": ["visual_signature:ffffffffffffffff"],
    }
    different = {**same, "constraints": ["visual_signature:0000000000000000"]}

    same_score = matcher.score(base, same)
    different_score = matcher.score(base, different)

    assert same_score["visual_score"] == 1.0
    assert different_score["visual_score"] == 0.0
    assert same_score["score"] > different_score["score"]
