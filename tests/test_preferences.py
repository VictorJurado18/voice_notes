from __future__ import annotations

import json
from pathlib import Path

from record_transcript_resume.preferences import (
    load_library_directory, load_summary_provider, save_library_directory,
    save_summary_provider,
)


def test_selected_summary_provider_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"

    save_summary_provider("api:azure-openai", path)

    assert load_summary_provider(path) == "api:azure-openai"
    assert json.loads(path.read_text(encoding="utf-8")) == {"summary_provider": "api:azure-openai"}


def test_missing_or_invalid_preferences_fall_back_without_error(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"
    path.write_text("not-json", encoding="utf-8")

    assert load_summary_provider(path) == ""


def test_library_directory_and_summary_provider_are_saved_independently(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"
    selected = str(tmp_path / "old-recordings")

    save_library_directory(selected, path)
    save_summary_provider("codex", path)
    assert load_library_directory(path) == selected
    assert load_summary_provider(path) == "codex"

    save_library_directory("", path)
    assert load_library_directory(path) == ""
    assert load_summary_provider(path) == "codex"
