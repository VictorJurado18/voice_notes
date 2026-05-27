from __future__ import annotations

from pathlib import Path


def default_output_dir() -> Path:
    music_dir = Path.home() / "Music"
    if music_dir.exists() or not Path("recordings").exists():
        return music_dir / "gravador_audio"
    return Path("recordings")
