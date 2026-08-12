from app.api.routes.webhook import _voice_transcription_diagnostic


def test_voice_transcription_diagnostic_includes_fallback_statuses_without_audio_content():
    diagnostic = _voice_transcription_diagnostic(
        {
            "success": False,
            "status": "GENERATE_CONTENT_TRANSCRIPTION_ERROR",
            "direct_status": "EMPTY_TRANSCRIPT",
            "normalization_status": "NORMALIZED",
            "normalized_status": "EMPTY_GENERATE_CONTENT_TRANSCRIPT",
            "secondary_original_fallback": True,
            "http_status": 429,
            "error": "quota",
            "content": b"secret-audio",
        }
    )

    assert "direct=EMPTY_TRANSCRIPT" in diagnostic
    assert "normalization=NORMALIZED" in diagnostic
    assert "normalized=EMPTY_GENERATE_CONTENT_TRANSCRIPT" in diagnostic
    assert "secondary_original=True" in diagnostic
    assert "http=429" in diagnostic
    assert "error=quota" in diagnostic
    assert "secret-audio" not in diagnostic
