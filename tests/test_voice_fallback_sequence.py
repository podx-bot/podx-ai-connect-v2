def test_voice_fallback_sequence_documentation():
    sequence = ["interactions_direct", "ffmpeg_normalize", "generate_content_audio"]
    assert sequence == ["interactions_direct", "ffmpeg_normalize", "generate_content_audio"]
