"""Small, non-secret preferences that should survive application restarts."""
from __future__ import annotations

import json
from pathlib import Path

from record_transcript_resume.paths import app_data_dir


def _path(path: Path | None = None) -> Path:
    return path or app_data_dir() / "preferences.json"


def _load(path: Path | None = None) -> dict[str, object]:
    try:
        payload = json.loads(_path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save(payload: dict[str, object], path: Path | None = None) -> None:
    target = _path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)


def load_summary_provider(path: Path | None = None) -> str:
    """Return the stable code for the provider selected for summaries.

    API keys deliberately do not live here; they remain in Windows Credential
    Manager.  An API provider is represented only by its generated id.
    """
    return str(_load(path).get("summary_provider", "")).strip()


def save_summary_provider(provider_code: str, path: Path | None = None) -> None:
    """Persist the selected provider atomically without storing credentials."""
    payload = _load(path)
    payload["summary_provider"] = provider_code.strip()
    _save(payload, path)


def load_library_directory(path: Path | None = None) -> str:
    """Return the last folder explicitly chosen for browsing the library."""
    value = _load(path).get("library_directory", "")
    return value.strip() if isinstance(value, str) else ""


def save_library_directory(directory: str, path: Path | None = None) -> None:
    """Persist a browsing folder; an empty value follows the recording folder."""
    payload = _load(path)
    if directory.strip():
        payload["library_directory"] = directory.strip()
    else:
        payload.pop("library_directory", None)
    _save(payload, path)
