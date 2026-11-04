from __future__ import annotations

import re
import tomllib
from pathlib import Path

from record_transcript_resume.release_notes import load_highlights


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_installer_version_matches_project_version() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    installer = (PROJECT_ROOT / "installer" / "VoiceNotes.iss").read_text(encoding="utf-8")
    match = re.search(r'^#define MyAppVersion "([^"]+)"$', installer, re.MULTILINE)

    assert match is not None
    assert match.group(1) == project["project"]["version"]
    assert "OutputBaseFilename=VoiceNotes-Setup-{#MyAppVersion}" in installer


def test_current_version_has_its_own_release_highlights() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    highlights = load_highlights(project["project"]["version"])

    assert len(highlights) >= 2
    assert all(title and detail for title, detail in highlights)
