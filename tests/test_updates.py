from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from unittest.mock import patch

from record_transcript_resume.updates import APP_VERSION, ApplicationUpdate, check_for_updates, start_downloaded_update


def test_installed_version_matches_project_metadata() -> None:
    contents = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    expected = re.search(r'^version\s*=\s*"([^"]+)"', contents, re.MULTILINE)
    assert expected is not None
    assert APP_VERSION == expected.group(1)


def _next_patch_version(version: str) -> str:
    major, minor, patch = version.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


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
    newer_version = _next_patch_version(APP_VERSION)
    with patch("record_transcript_resume.updates._latest_release_payload", return_value=_release(newer_version)):
        result = check_for_updates()

    assert result == ApplicationUpdate(
        available=True,
        message=f"Nova versão disponível: {newer_version}.",
        version=newer_version,
        download_url="https://example.test/VoiceNotes-Setup.exe",
        sha256="abc123",
    )


def test_check_for_updates_ignores_current_or_older_release() -> None:
    with patch("record_transcript_resume.updates._latest_release_payload", return_value=_release(APP_VERSION)):
        result = check_for_updates()

    assert result.available is False
    assert "já está atualizado" in result.message


def test_check_for_updates_requires_the_windows_setup_asset() -> None:
    with patch("record_transcript_resume.updates._latest_release_payload", return_value=_release(APP_VERSION, "source.zip")):
        result = check_for_updates()

    assert result.available is False
    assert "instalador" in result.message


def test_update_launcher_waits_for_the_app_to_exit_before_running_setup(tmp_path) -> None:
    updates_dir = tmp_path / "Voice Notes updates"
    updates_dir.mkdir()
    installer = updates_dir / "VoiceNotes-Setup-0.10.17.exe"
    installer.write_bytes(b"installer")
    update = ApplicationUpdate(True, "Pronto", "0.10.17", installer_path=str(installer))

    with patch("record_transcript_resume.updates.subprocess.Popen") as start_process:
        result = start_downloaded_update(update)

    assert result.available is True
    command = start_process.call_args.args[0]
    assert command.startswith('cmd.exe /d /c call "')
    launcher = updates_dir / "start-update.cmd"
    assert launcher.is_file()
    launcher_contents = launcher.read_text(encoding="ascii")
    assert ":wait_for_voice_notes" in launcher_contents
    assert "tasklist /FI" in launcher_contents
    assert "/VERYSILENT" in launcher_contents


def test_update_launcher_executes_from_a_path_with_spaces(tmp_path) -> None:
    """Run the generated Windows command instead of only asserting its shape."""
    updates_dir = tmp_path / "Voice Notes updates"
    updates_dir.mkdir()
    installer = updates_dir / "Fake Voice Notes Setup.cmd"
    installer.write_text(
        '@echo off\r\n> "%~dp0installer-ran.txt" echo installer-ran\r\nexit /b 0\r\n',
        encoding="ascii",
    )
    update = ApplicationUpdate(True, "Pronto", "0.10.19", installer_path=str(installer))

    with patch("record_transcript_resume.updates.subprocess.Popen") as start_process:
        result = start_downloaded_update(update)

    assert result.available is True
    command = start_process.call_args.args[0].replace(str(os.getpid()), "2147483647", 1)
    subprocess.run(command, cwd=str(updates_dir), check=True, timeout=10)

    assert (updates_dir / "installer-ran.txt").read_text(encoding="ascii").strip() == "installer-ran"
