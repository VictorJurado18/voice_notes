"""Read-only discovery helpers for the user's local recording library."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class LibraryItem:
    folder: Path
    mp3_path: Path | None
    transcript_path: Path | None
    summary_path: Path | None
    title: str
    modified_at: datetime
    summary_available: bool

    @property
    def searchable_text(self) -> str:
        return f"{self.title} {self.folder.name}".casefold()


def discover_recordings(output_dir: Path) -> list[LibraryItem]:
    """Find completed or partially completed Voice Notes folders, newest first."""
    try:
        folders = [entry for entry in output_dir.iterdir() if entry.is_dir()]
    except OSError:
        return []

    items: list[LibraryItem] = []
    for folder in folders:
        transcript = folder / "transcription.md"
        summary = folder / "summary.md"
        mp3 = next(iter(folder.glob("*.mp3")), None)
        if not transcript.is_file() and not summary.is_file() and mp3 is None:
            continue
        summary_available = summary.is_file() and "# Summary unavailable" not in _read_text(summary)
        items.append(
            LibraryItem(
                folder=folder,
                mp3_path=mp3,
                transcript_path=transcript if transcript.is_file() else None,
                summary_path=summary if summary.is_file() else None,
                title=_title(summary, transcript, folder.name),
                modified_at=datetime.fromtimestamp(folder.stat().st_mtime),
                summary_available=summary_available,
            )
        )
    for mp3 in output_dir.glob("*.mp3"):
        # Audio is deliberately discoverable before any AI work begins.  This
        # also keeps a failed transcription visible and easy to open.
        items.append(
            LibraryItem(
                folder=output_dir,
                mp3_path=mp3,
                transcript_path=None,
                summary_path=None,
                title=mp3.stem.replace("-", " ").replace("_", " ").title(),
                modified_at=datetime.fromtimestamp(mp3.stat().st_mtime),
                summary_available=False,
            )
        )
    return sorted(items, key=lambda item: item.modified_at, reverse=True)


def _title(summary_path: Path, transcript_path: Path, fallback: str) -> str:
    for path in (summary_path, transcript_path):
        text = _read_text(path)
        for line in text.splitlines():
            if line.startswith("# ") and line.strip().casefold() not in {"# transcription", "# summary unavailable"}:
                return line[2:].strip()
    return fallback.replace("-", " ").replace("_", " ").title()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""
