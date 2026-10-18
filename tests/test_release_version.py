from __future__ import annotations

import re
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_installer_version_matches_project_version() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    installer = (PROJECT_ROOT / "installer" / "VoiceNotes.iss").read_text(encoding="utf-8")
    match = re.search(r'^#define MyAppVersion "([^"]+)"$', installer, re.MULTILINE)

    assert match is not None
    assert match.group(1) == project["project"]["version"]
    assert "OutputBaseFilename=VoiceNotes-Setup-{#MyAppVersion}" in installer
