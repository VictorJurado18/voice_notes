"""User-defined summary profiles stored separately from recordings."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from uuid import uuid4

from record_transcript_resume.paths import app_data_dir


@dataclass(frozen=True)
class SummaryProfile:
    """A reusable summary instruction set chosen before processing."""

    id: str = ""
    name: str = "Meu perfil"
    base_template: str = "meeting"
    instructions: str = ""
    model_size: str = "small"
    separate_speakers: bool = False


def _path(path: Path | None = None) -> Path:
    return path or app_data_dir() / "summary-profiles.json"


def load_profiles(path: Path | None = None) -> list[SummaryProfile]:
    """Load user profiles, ignoring damaged individual entries safely."""
    try:
        payload = json.loads(_path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return []
    entries = payload.get("profiles", []) if isinstance(payload, dict) else []
    if not isinstance(entries, list):
        return []
    profiles: list[SummaryProfile] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            profile = SummaryProfile(**entry)
        except TypeError:
            continue
        if profile.id and profile.name.strip():
            profiles.append(profile)
    return profiles


def save_profile(profile: SummaryProfile, path: Path | None = None) -> SummaryProfile:
    """Create or update a profile without overwriting the other profiles."""
    name = profile.name.strip()
    instructions = profile.instructions.strip()
    if not name:
        raise ValueError("Informe um nome para o perfil.")
    if not instructions:
        raise ValueError("Descreva como o resumo deve ser organizado.")
    saved = replace(profile, id=profile.id or uuid4().hex, name=name, instructions=instructions)
    target = _path(path)
    existing = load_profiles(target)
    if any(item.id != saved.id and item.name.casefold() == saved.name.casefold() for item in existing):
        raise ValueError("Já existe um perfil com esse nome.")
    result = [saved if item.id == saved.id else item for item in existing]
    if not any(item.id == saved.id for item in existing):
        result.append(saved)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"profiles": [asdict(item) for item in result]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return saved


def get_profile(profile_id: str, path: Path | None = None) -> SummaryProfile | None:
    return next((item for item in load_profiles(path) if item.id == profile_id), None)
