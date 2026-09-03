"""Small, non-secret preferences that should survive application restarts."""
from __future__ import annotations

import json
from pathlib import Path

from record_transcript_resume.paths import app_data_dir


def _path(path: Path | None = None) -> Path:
    return path or app_data_dir() / "preferences.json"


def load_summary_provider(path: Path | None = None) -> str:
    """Return the stable code for the provider selected for summaries.

    API keys deliberately do not live here; they remain in Windows Credential
    Manager.  An API provider is represented only by its generated id.
    """
    try:
        payload = json.loads(_path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("summary_provider", "")).strip()


def save_summary_provider(provider_code: str, path: Path | None = None) -> None:
    """Persist the selected provider atomically without storing credentials."""
    target = _path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"summary_provider": provider_code.strip()}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
