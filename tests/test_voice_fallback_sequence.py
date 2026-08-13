def test_voice_fallback_sequence_documentation():
    sequence = [
        "ffmpeg_normalize",
        "normalized_generate_content",
        "original_generate_content",
        "interactions_last_resort",
    ]
    assert sequence == [
        "ffmpeg_normalize",
        "normalized_generate_content",
        "original_generate_content",
        "interactions_last_resort",
    ]
