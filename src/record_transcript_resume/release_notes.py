"""Offline release highlights and per-user, per-version announcement state."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from record_transcript_resume.paths import app_data_dir


def _version(value: object) -> tuple[int, ...] | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d+){1,3}", value):
        return None
    parts = tuple(map(int, value.split(".")))
    return parts + (0,) * (4 - len(parts))


def load_highlights(version: str) -> tuple[tuple[str, str], ...]:
    """Load the notes shipped with this exact version of the app."""
    if _version(version) is None:
        raise ValueError("Versão inválida para as notas de lançamento.")
    path = Path(__file__).resolve().parent / "resources" / "release-notes" / f"{version}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Notas da versão {version} não encontradas ou inválidas.") from exc
    if not isinstance(data, dict) or data.get("version") != version:
        raise ValueError(f"As notas não correspondem à versão {version}.")
    entries = data.get("highlights")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"A versão {version} não tem novidades descritas.")
    highlights: list[tuple[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Formato inválido das notas de lançamento.")
        heading, detail = entry.get("title"), entry.get("detail")
        if not isinstance(heading, str) or not heading.strip() or not isinstance(detail, str) or not detail.strip():
            raise ValueError("Uma novidade está sem título ou descrição.")
        highlights.append((heading.strip(), detail.strip()))
    return tuple(highlights)


def _install_history() -> tuple[str, str]:
    """The installer captures the old version before replacing its registry entry."""
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Voice Notes\InstallHistory") as key:
                current = winreg.QueryValueEx(key, "Version")[0]
                previous = winreg.QueryValueEx(key, "PreviousVersion")[0]
            if _version(current) and _version(previous):
                return current, previous
        except (OSError, ValueError):
            pass
    return "", ""


@dataclass(frozen=True)
class ReleaseNotice:
    version: str
    previous_version: str = ""
    pending: bool = False


class ReleaseNoticeStore:
    """Keep announcement state separate from themes and provider preferences."""

    def __init__(self, path: Path | None = None, *, development: bool = False) -> None:
        self.path = path or app_data_dir() / (
            "release-notices-dev.json" if development else "release-notices.json"
        )
        self.development = development

    def _load(self) -> dict[str, object]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def has_seen(self, version: str) -> bool:
        current = _version(version)
        seen = _version(self._load().get("highest_seen_version"))
        return current is not None and seen is not None and current <= seen

    def prepare(self, version: str) -> ReleaseNotice:
        """Detect upgrades without consuming an announcement hidden in the tray.

        First installs establish a baseline. The installer's previous version
        also detects the first upgrade from releases without this feature.
        A downgrade or reinstall cannot reannounce a version already seen.
        """
        current = _version(version)
        if current is None or current == (0, 0, 0, 0):
            return ReleaseNotice(version)
        data = self._load()
        launched = data.get("last_launched_version", "")
        previous = data.get("updated_from", "") if launched == version else launched
        if not _version(previous) and not self.development:
            installed, installed_from = _install_history()
            if _version(installed) == current:
                previous = installed_from
        previous_key = _version(previous)
        seen = _version(data.get("highest_seen_version"))
        upgraded = previous_key is not None and previous_key < current
        pending = upgraded and (seen is None or seen < current)
        if not _version(launched) and not upgraded:
            # A genuinely new installation has no earlier version to describe.
            if seen is None or seen < current:
                data["highest_seen_version"] = version
        data["last_launched_version"] = version
        data["updated_from"] = previous if upgraded else ""
        self._save(data)
        return ReleaseNotice(version, str(previous) if upgraded else "", pending)

    def mark_seen(self, version: str) -> None:
        current = _version(version)
        if current is None:
            return
        data = self._load()
        seen = _version(data.get("highest_seen_version"))
        if seen is None or current > seen:
            data["highest_seen_version"] = version
            self._save(data)
