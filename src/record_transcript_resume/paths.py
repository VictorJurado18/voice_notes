from __future__ import annotations

import os
from pathlib import Path


def app_data_dir() -> Path:
    """Return a per-user writable location for installed application data."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "Voice Notes"


def default_output_dir() -> Path:
    music_dir = Path.home() / "Music"
    if music_dir.exists() or not Path("recordings").exists():
        return music_dir / "record-transcript-resume"
    return Path("recordings")
