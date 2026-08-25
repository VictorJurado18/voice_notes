from __future__ import annotations

from unittest.mock import patch

from record_transcript_resume.updates import APP_VERSION, ApplicationUpdate, check_for_updates


def test_installed_version_matches_project_metadata() -> None:
    assert APP_VERSION == "0.10.16"


def _release(version: str, asset_name: str | None = None) -> dict[str, object]:
    return {
        "tag_name": f"v{version}",
        "assets": [{
            "name": asset_name or f"VoiceNotes-Setup-{version}.exe",
            "browser_download_url": "https://example.test/VoiceNotes-Setup.exe",
            "digest": "sha256:abc123",
        }],
    }


def test_check_for_updates_offers_a_newer_published_installer() -> None:
    with patch("record_transcript_resume.updates._latest_release_payload", return_value=_release("0.10.17")):
        result = check_for_updates()

    assert result == ApplicationUpdate(
        available=True,
        message="Nova versão disponível: 0.10.17.",
        version="0.10.17",
        download_url="https://example.test/VoiceNotes-Setup.exe",
        sha256="abc123",
    )


def test_check_for_updates_ignores_current_or_older_release() -> None:
    with patch("record_transcript_resume.updates._latest_release_payload", return_value=_release("0.10.16")):
        result = check_for_updates()

    assert result.available is False
    assert "já está atualizado" in result.message


def test_check_for_updates_requires_the_windows_setup_asset() -> None:
    with patch("record_transcript_resume.updates._latest_release_payload", return_value=_release("0.10.16", "source.zip")):
        result = check_for_updates()

    assert result.available is False
    assert "instalador" in result.message
