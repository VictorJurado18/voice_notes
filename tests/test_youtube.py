from __future__ import annotations

from record_transcript_resume.youtube import _friendly_download_error, is_supported_youtube_url, normalize_youtube_url


def test_accepts_common_youtube_video_urls() -> None:
    assert is_supported_youtube_url("https://www.youtube.com/watch?v=abc")
    assert is_supported_youtube_url("https://youtu.be/abc")
    assert is_supported_youtube_url("https://m.youtube.com/watch?v=abc")
    assert is_supported_youtube_url("youtu.be/abc")
    assert normalize_youtube_url("youtube.com/watch?v=abc") == "https://youtube.com/watch?v=abc"


def test_rejects_non_youtube_hosts() -> None:
    assert not is_supported_youtube_url("https://example.com/watch?v=abc")
    assert not is_supported_youtube_url("not a url")


def test_translates_youtube_access_block_into_recovery_message() -> None:
    message = _friendly_download_error("ERROR: Sign in to confirm you're not a bot")

    assert "bloqueou" in message
    assert "Tente novamente" in message


def test_translates_drm_protection_into_recovery_message() -> None:
    message = _friendly_download_error("This video is DRM protected")

    assert "protegido" in message
