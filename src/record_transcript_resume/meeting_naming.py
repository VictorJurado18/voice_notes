"""Safe content names for one meeting, without touching shared directories."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
import json
import hashlib
from pathlib import Path
import re
import unicodedata

from record_transcript_resume.meeting_topics import METADATA_NAME, is_internal_metadata, summary_available

MEDIA_SUFFIXES = frozenset({
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma",
    ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi",
})


def safe_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    name = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")[:60].rstrip("-")
    if re.fullmatch(r"con|prn|aux|nul|com[0-9]|lpt[0-9]", name):
        name = f"reuniao-{name}"
    return name


def recording_time(path: Path) -> datetime | None:
    match = re.fullmatch(r"recording-(\d{8})-(\d{6})", path.stem, re.IGNORECASE)
    if match:
        try:
            return datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
        except ValueError:
            pass
    folder = path if path.is_dir() else path.parent
    try:
        metadata = folder / METADATA_NAME
        stat = metadata.stat()
        data = _recording_metadata(str(metadata), stat.st_mtime_ns, stat.st_size)
        if path == folder or path.name == data.get("audio_file"):
            return datetime.fromisoformat(str(data["recorded_at"])).replace(tzinfo=None)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


@lru_cache(maxsize=512)
def _recording_metadata(path: str, *_stat: int) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def is_meeting_folder(audio: Path) -> bool:
    """Only move a dedicated, non-linked folder with one media file and app outputs."""
    folder = audio.parent
    if folder.is_symlink() or folder.is_junction() or audio.is_symlink():
        return False
    try:
        children = list(folder.iterdir())
        if any(child.is_symlink() or child.is_junction() or child.is_dir() for child in children):
            return False
        if [child for child in children if child.suffix.casefold() in MEDIA_SUFFIXES] != [audio]:
            return False
        if any(child != audio and child.name not in {
            "transcription.md", "summary.md", "transcription.pdf", "summary.pdf",
            "transcription.docx", "summary.docx",
        } and not is_internal_metadata(child) for child in children):
            return False
        return folder.name.casefold() == audio.stem.casefold() or any(
            child.name in {METADATA_NAME, "transcription.md", "summary.md"} for child in children
        )
    except OSError:
        return False


@dataclass(frozen=True)
class NamingResult:
    audio: Path
    moved_folder: Path | None = None
    warning: str = ""


def saved_meeting_audio(path: Path) -> Path | None:
    """Resolve one processed meeting; never guess which audio a shared summary describes."""
    folder = path if path.is_dir() else path.parent
    try:
        media = [child for child in folder.iterdir() if child.is_file() and child.suffix.casefold() in MEDIA_SUFFIXES]
        if len(media) != 1 or not is_meeting_folder(media[0]):
            return None
        if summary_available(folder) or (folder / "transcription.md").is_file():
            return media[0]
    except OSError:
        pass
    return None


@dataclass(frozen=True)
class NameSource:
    audio: Path
    document: Path
    digest: str
    audio_size: int
    audio_mtime_ns: int

    def validate(self) -> None:
        stat = self.audio.stat()
        if (not is_meeting_folder(self.audio) or stat.st_size != self.audio_size
                or stat.st_mtime_ns != self.audio_mtime_ns
                or self.document.is_symlink()
                or hashlib.sha256(self.document.read_bytes()).hexdigest() != self.digest):
            raise ValueError("Os arquivos desta gravação mudaram durante a sugestão. Gere um novo nome antes de aplicar.")


def load_name_source(audio: Path) -> tuple[NameSource, str]:
    if saved_meeting_audio(audio) != audio:
        raise ValueError("Selecione a pasta de uma gravação processada que contenha um único áudio.")
    document = audio.parent / ("summary.md" if summary_available(audio.parent) else "transcription.md")
    if document.is_symlink():
        raise ValueError("Não é possível usar um documento vinculado para renomear a gravação.")
    original = document.read_bytes()
    text = original.decode("utf-8-sig").strip()
    if not text:
        raise ValueError("O documento salvo está vazio. Não foi possível identificar o assunto.")
    stat = audio.stat()
    return NameSource(audio, document, hashlib.sha256(original).hexdigest(), stat.st_size, stat.st_mtime_ns), text


def plan_meeting_name(audio: Path, suggested_name: str) -> tuple[Path, Path]:
    base = safe_name(suggested_name)
    if not base:
        raise ValueError("Informe um nome válido para a gravação.")
    folder = audio.parent
    suffix = 1
    while True:
        name = base if suffix == 1 else f"{base}-{suffix}"
        destination = folder.with_name(name)
        renamed_audio = folder / (name + audio.suffix)
        folder_taken = destination != folder and (destination.exists() or destination.is_symlink())
        audio_taken = renamed_audio != audio and (renamed_audio.exists() or renamed_audio.is_symlink())
        if not folder_taken and not audio_taken:
            return destination, renamed_audio
        suffix += 1


def rename_meeting(audio: Path, suggested_name: str) -> NamingResult:
    """Rename in the same parent. A failure never invalidates saved output paths."""
    base = safe_name(suggested_name)
    if not base:
        return NamingResult(audio)
    folder = audio.parent
    # is_symlink in the planner also detects dangling links, which must never be replaced.
    destination, renamed_audio = plan_meeting_name(audio, base)
    actual = audio
    try:
        if renamed_audio != audio:
            audio.rename(renamed_audio)
            actual = renamed_audio
        if destination != folder:
            folder.rename(destination)
            return NamingResult(destination / actual.name, moved_folder=folder)
        return NamingResult(actual)
    except OSError as exc:
        # The folder may be locked by an external player/Explorer on Windows.
        if actual != audio:
            try:
                actual.rename(audio)
                actual = audio
            except OSError:
                pass
        return NamingResult(actual, warning=(
            "O processamento foi salvo, mas não foi possível aplicar o nome sugerido. "
            f"Pasta atual: {actual.parent.name}. Detalhes: {exc}"
        ))
