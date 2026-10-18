"""Read-only discovery helpers for the user's local recording library."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
import json
import re
from pathlib import Path
from typing import Literal

from record_transcript_resume.paths import app_data_dir


MEDIA_SUFFIXES = frozenset({
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma",
    ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi",
})


def _item_key(path: Path) -> str:
    return str(path.resolve()).casefold()


class LibraryMetadataStore:
    """User titles, tags and favorites without changing recording files."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_dir() / "library-metadata.json"

    def load(self) -> dict[str, dict[str, object]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(
        self, item_path: Path, *, title: str | None = None,
        tags: tuple[str, ...] | None = None, favorite: bool | None = None,
    ) -> None:
        data = self.load()
        key = _item_key(item_path)
        previous = data.get(key, {})
        if not isinstance(previous, dict):
            previous = {}
        data[key] = {
            "title": title.strip()[:160] if title is not None else str(previous.get("title", "")),
            "tags": (
                list(dict.fromkeys(tag.strip()[:40] for tag in tags if tag.strip()))[:12]
                if tags is not None else previous.get("tags", [])
            ),
            "favorite": bool(favorite) if favorite is not None else bool(previous.get("favorite", False)),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def transfer(self, source: Path, destination: Path, *, keep_source: bool = False) -> None:
        if _item_key(source) == _item_key(destination):
            return
        data = self.load()
        source_key = _item_key(source)
        if source_key not in data:
            return
        data[_item_key(destination)] = data[source_key]
        if not keep_source:
            del data[source_key]
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def relocate_tree(self, source: Path, destination: Path) -> None:
        """Keep titles, tags and favorites attached when a folder is moved."""
        data = self.load()
        source_key = _item_key(source)
        destination_key = _item_key(destination)
        moved = {}
        for key, value in list(data.items()):
            if key == source_key or key.startswith(source_key + str(Path('/'))):
                moved[destination_key + key[len(source_key):]] = value
                del data[key]
        if moved:
            data.update(moved)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)


@dataclass(frozen=True)
class BrowserEntry:
    """One immediate child of a directory, as a file explorer would show it."""

    path: Path
    kind: Literal["folder", "recording", "text_record", "audio", "document", "file"]
    title: str
    detail: str
    modified_at: datetime


def browse_directory(directory: Path, metadata_store: LibraryMetadataStore | None = None) -> list[BrowserEntry]:
    """List only this directory; never flatten nested folders into the same view."""
    try:
        children = list(directory.iterdir())
    except OSError:
        return []
    metadata = (metadata_store or LibraryMetadataStore()).load()
    entries: list[BrowserEntry] = []
    for child in children:
        try:
            is_dir = child.is_dir()
            is_file = child.is_file()
            modified = datetime.fromtimestamp(child.stat().st_mtime)
        except OSError:
            continue
        if not (is_dir or is_file):
            continue
        kind: Literal["folder", "recording", "text_record", "audio", "document", "file"]
        detail = ""
        media: Path | None = None
        if is_dir:
            try:
                inside = list(child.iterdir())
            except OSError:
                inside = []
            media = next((path for path in inside if path.is_file() and path.suffix.casefold() in MEDIA_SUFFIXES), None)
            has_documents = any(path.name.casefold() in {"transcription.md", "summary.md"} for path in inside)
            kind = "recording" if media else "text_record" if has_documents else "folder"
            if kind in {"recording", "text_record"}:
                parts = [label for present, label in (
                    (media is not None, "Áudio"),
                    (any(path.name.casefold() == "transcription.md" for path in inside), "transcrição"),
                    (any(path.name.casefold() == "summary.md" for path in inside), "resumo"),
                ) if present]
                detail = " + ".join(parts)
            else:
                count = len(inside)
                detail = f"{count} {'item' if count == 1 else 'itens'}"
        elif child.suffix.casefold() in MEDIA_SUFFIXES:
            kind = "audio"
            detail = child.suffix[1:].upper()
        elif child.suffix.casefold() in {".md", ".txt", ".docx", ".pdf", ".rtf"}:
            kind = "document"
            detail = "Transcrição" if child.name.casefold() == "transcription.md" else "Resumo" if child.name.casefold() == "summary.md" else child.suffix[1:].upper()
        else:
            kind = "file"
            detail = child.suffix[1:].upper() if child.suffix else "Arquivo"
        user_data = metadata.get(_item_key(media or child), {})
        title = str(user_data.get("title") or _default_title(child.stem)) if isinstance(user_data, dict) and kind in {"recording", "text_record"} else child.name
        entries.append(BrowserEntry(child, kind, title, detail, modified))
    return sorted(entries, key=lambda entry: (entry.title.casefold(), entry.path.name.casefold()))


@dataclass(frozen=True)
class LibraryItem:
    folder: Path
    mp3_path: Path | None
    transcript_path: Path | None
    summary_path: Path | None
    title: str
    modified_at: datetime
    summary_available: bool
    tags: tuple[str, ...] = ()
    favorite: bool = False
    has_own_folder: bool = False
    recorded_at: datetime | None = None
    nested_in: str = ""

    @property
    def sort_at(self) -> datetime:
        return self.recorded_at or self.modified_at

    @property
    def contents_label(self) -> str:
        parts = [
            label for available, label in (
                (self.mp3_path is not None, "Áudio"),
                (self.transcript_path is not None, "Transcrição"),
                (self.summary_available, "Resumo"),
            ) if available
        ]
        if not parts:
            return "Resumo com falha"
        return f"Só {parts[0]}" if len(parts) == 1 else " + ".join(parts)

    @property
    def next_step_label(self) -> str:
        if self.summary_path is not None and not self.summary_available:
            return "Resumo com falha · tente gerar novamente"
        if self.transcript_path is not None and not self.summary_available:
            return "Pronto para gerar resumo"
        if self.mp3_path is not None and self.transcript_path is None and not self.summary_available:
            return "Pronto para transcrever"
        return "Pronto para consultar"

    @property
    def searchable_text(self) -> str:
        media_name = self.mp3_path.name if self.mp3_path else ""
        return f"{self.title} {self.folder.name} {media_name} {' '.join(self.tags)}".casefold()


def discover_recordings(output_dir: Path, metadata_store: LibraryMetadataStore | None = None) -> list[LibraryItem]:
    """Find completed or partially completed Voice Notes folders, newest first."""
    try:
        entries = list(output_dir.iterdir())
    except OSError:
        return []

    metadata = (metadata_store or LibraryMetadataStore()).load()
    items: list[LibraryItem] = []
    root_transcript = output_dir / "transcription.md"
    root_summary = output_dir / "summary.md"
    root_media: Path | None = None
    if root_transcript.is_file() or root_summary.is_file():
        root_media = next(
            (entry for entry in entries if entry.is_file() and entry.suffix.casefold() in MEDIA_SUFFIXES),
            None,
        )
        summary_header = _read_head(root_summary)
        transcript_header = _read_head(root_transcript)
        user_data = metadata.get(_item_key(root_media or output_dir), {})
        if not isinstance(user_data, dict):
            user_data = {}
        tags = user_data.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        items.append(
            LibraryItem(
                folder=output_dir,
                mp3_path=root_media,
                transcript_path=root_transcript if root_transcript.is_file() else None,
                summary_path=root_summary if root_summary.is_file() else None,
                title=str(user_data.get("title") or _title(summary_header, transcript_header, output_dir.name)),
                modified_at=datetime.fromtimestamp(output_dir.stat().st_mtime),
                summary_available=root_summary.is_file() and "# Summary unavailable" not in summary_header,
                tags=tuple(tag for tag in tags if isinstance(tag, str)),
                favorite=bool(user_data.get("favorite", False)),
                has_own_folder=True,
                recorded_at=_recording_time(root_media),
            )
        )
    folders: list[Path] = []
    for entry in entries:
        if not entry.is_dir():
            continue
        folders.append(entry)
        # Older versions could create a result folder inside an existing
        # recording folder. Keep those recordings discoverable without moving
        # the user's files during a library refresh.
        try:
            folders.extend(child for child in entry.iterdir() if child.is_dir())
        except OSError:
            pass
    for folder in folders:
        transcript = folder / "transcription.md"
        summary = folder / "summary.md"
        try:
            media = next((entry for entry in folder.iterdir() if entry.is_file() and entry.suffix.casefold() in MEDIA_SUFFIXES), None)
        except OSError:
            media = None
        if not transcript.is_file() and not summary.is_file() and media is None:
            continue
        summary_header = _read_head(summary)
        transcript_header = _read_head(transcript)
        summary_available = summary.is_file() and "# Summary unavailable" not in summary_header
        user_data = metadata.get(_item_key(media or folder), {})
        if not isinstance(user_data, dict):
            user_data = {}
        tags = user_data.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        items.append(
            LibraryItem(
                folder=folder,
                mp3_path=media,
                transcript_path=transcript if transcript.is_file() else None,
                summary_path=summary if summary.is_file() else None,
                title=str(user_data.get("title") or _title(summary_header, transcript_header, folder.name)),
                modified_at=datetime.fromtimestamp(folder.stat().st_mtime),
                summary_available=summary_available,
                tags=tuple(tag for tag in tags if isinstance(tag, str)),
                favorite=bool(user_data.get("favorite", False)),
                has_own_folder=True,
                recorded_at=_recording_time(media),
                nested_in=folder.parent.name if folder.parent != output_dir else "",
            )
        )
    for media in (entry for entry in entries if entry.is_file() and entry.suffix.casefold() in MEDIA_SUFFIXES):
        if media == root_media:
            continue
        # Audio is deliberately discoverable before any AI work begins.  This
        # also keeps a failed transcription visible and easy to open.
        user_data = metadata.get(_item_key(media), {})
        if not isinstance(user_data, dict):
            user_data = {}
        tags = user_data.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        items.append(
            LibraryItem(
                folder=output_dir,
                mp3_path=media,
                transcript_path=None,
                summary_path=None,
                title=str(user_data.get("title") or _default_title(media.stem)),
                modified_at=datetime.fromtimestamp(media.stat().st_mtime),
                summary_available=False,
                tags=tuple(tag for tag in tags if isinstance(tag, str)),
                favorite=bool(user_data.get("favorite", False)),
                has_own_folder=output_dir.name.casefold() == media.stem.casefold(),
                recorded_at=_recording_time(media),
            )
        )
    return sorted(items, key=lambda item: item.sort_at, reverse=True)


def _recording_time(media: Path | None) -> datetime | None:
    if media is None:
        return None
    match = re.fullmatch(r"recording-(\d{8})-(\d{6})", media.stem, flags=re.IGNORECASE)
    if match is None:
        return None
    try:
        return datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _title(summary_header: str, transcript_header: str, fallback: str) -> str:
    for text in (summary_header, transcript_header):
        for line in text.splitlines():
            if line.startswith("# ") and line.strip().casefold() not in {"# transcription", "# summary unavailable"}:
                return line[2:].strip()
    return _default_title(fallback)


def _default_title(name: str) -> str:
    if name.casefold().startswith("recording-recording-"):
        name = name[len("recording-"):]
    match = re.fullmatch(r"recording-(\d{8})-(\d{6})", name, flags=re.IGNORECASE)
    if match is not None:
        try:
            recorded = datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
            return f"Gravação de {recorded:%d/%m às %H:%M}"
        except ValueError:
            pass
    return name.replace("-", " ").replace("_", " ").title()


def _read_head(path: Path) -> str:
    try:
        stat = path.stat()
        return _cached_head(str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return ""


@lru_cache(maxsize=2048)
def _cached_head(path: str, modified_ns: int, size: int) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as document:
        return document.read(8192)
