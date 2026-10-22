"""Portable, optional meeting descriptions. No provider calls during browsing."""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

METADATA_NAME = ".voice-notes.json"


def normalize_topic(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"\s+", " ", value).strip(' \"\'`#')
    text = " ".join(text.split()[:12])
    if len(text) > 100:
        text = text[:97].rsplit(" ", 1)[0] + "…"
    return text


def summary_available(folder: Path) -> bool:
    try:
        with (folder / "summary.md").open(encoding="utf-8-sig") as source:
            start = source.read(512).strip()
        return bool(start) and not start.startswith("# Summary unavailable")
    except (OSError, UnicodeError):
        return False


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_topic(folder: Path, topic: str, *, summary_bytes: bytes | None = None) -> None:
    topic = normalize_topic(topic)
    if not topic:
        return
    fingerprint = _digest(folder / "summary.md")
    if summary_bytes is not None:
        expected = hashlib.sha256(summary_bytes).hexdigest()
        if fingerprint != expected:
            raise OSError("O resumo mudou durante a geração. Tente novamente.")
        fingerprint = expected
    save_metadata(folder, topic=topic, summary_sha256=fingerprint)
    _load_cached.cache_clear()


def save_metadata(folder: Path, **values: object) -> None:
    """Merge portable meeting metadata without discarding topic or recording date."""
    metadata = folder / METADATA_NAME
    if metadata.is_symlink() or metadata.is_junction():
        raise OSError("O arquivo de descrição não pode ser um link.")
    data: dict = {}
    try:
        existing = json.loads(metadata.read_text(encoding="utf-8"))
        if isinstance(existing, dict):
            data = existing
    except (OSError, ValueError, UnicodeError):
        pass
    data.update(values, schema=1)
    # An exclusive temporary file avoids following pre-existing links.
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder,
                            prefix=".voice-notes-", suffix=".tmp", delete=False) as output:
        temporary = Path(output.name)
        json.dump(data, output, ensure_ascii=False, indent=2)
    try:
        temporary.replace(metadata)
    finally:
        temporary.unlink(missing_ok=True)


def load_topic(folder: Path) -> str:
    try:
        summary = folder / "summary.md"
        metadata = folder / METADATA_NAME
        s, m = summary.stat(), metadata.stat()
        return _load_cached(str(folder), s.st_mtime_ns, s.st_size, m.st_mtime_ns, m.st_size)
    except OSError:
        return ""


@lru_cache(maxsize=256)
def _load_cached(folder_name: str, *_fingerprints: int) -> str:
    folder = Path(folder_name)
    try:
        data = json.loads((folder / METADATA_NAME).read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("summary_sha256") == _digest(folder / "summary.md"):
            return normalize_topic(data.get("topic"))
    except (OSError, ValueError, UnicodeError):
        pass
    return ""


def is_internal_metadata(path: Path) -> bool:
    return path.name == METADATA_NAME or (
        path.name.startswith(".voice-notes-") and path.suffix == ".tmp"
    )
