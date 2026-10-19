from __future__ import annotations

import json
from pathlib import Path

import pytest

from record_transcript_resume.preferences import (
    load_color_theme, load_library_directory, load_summary_provider,
    save_color_theme, save_library_directory, save_summary_provider,
)
from record_transcript_resume.themes import THEMES, theme_color


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


def test_color_theme_is_persisted_and_invalid_values_fall_back(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"

    save_color_theme("machine_red", path)

    assert load_color_theme(path) == "machine_red"
    save_summary_provider("claude", path)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "color_theme": "machine_red", "summary_provider": "claude",
    }
    path.write_text('{"color_theme":"not-a-theme"}', encoding="utf-8")
    assert load_color_theme(path) == "violeta"


@pytest.mark.parametrize("name", THEMES)
def test_every_theme_survives_other_preference_writes(name: str, tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"
    save_color_theme(name, path)
    save_library_directory(str(tmp_path / "Biblioteca"), path)
    save_summary_provider("claude", path)

    assert load_color_theme(path) == name
    assert load_summary_provider(path) == "claude"


def test_color_theme_rejects_unknown_names_and_machine_red_uses_requested_hexes() -> None:
    with pytest.raises(ValueError):
        save_color_theme("inexistente")

    palette = THEMES["machine_red"]
    assert palette["accent"] == "#FF2E3A"
    assert palette["soft"] == "#DBF6FF"
    assert theme_color("#6656D8", "machine_red") == "#FF2E3A"
    assert theme_color("#010203", "machine_red") == "#010203"
    assert theme_color("#141E32", "violeta") == "#141E32"
