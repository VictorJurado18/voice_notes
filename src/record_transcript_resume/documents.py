"""Local document helpers for imported and editable transcriptions."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def create_imported_transcript(text: str, output_dir: Path, title: str = "") -> Path:
    """Save pasted/imported text as a normal Voice Notes transcription."""
    body = _transcript_body(text)
    if not body:
        raise ValueError("A transcrição está vazia.")
    folder = _unique_folder(output_dir, title or "transcricao-importada")
    folder.mkdir(parents=True, exist_ok=False)
    transcript = folder / "transcription.md"
    transcript.write_text(f"# Transcrição\n\n{body}\n", encoding="utf-8")
    return transcript


def _transcript_body(text: str) -> str:
    value = text.strip()
    for heading in ("# Transcrição", "# Transcription"):
        if value.casefold().startswith(heading.casefold()):
            return value[len(heading):].lstrip(" \t\r\n")
    return value


def _unique_folder(output_dir: Path, title: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-") or "transcricao-importada"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = output_dir / f"{slug}-{stamp}"
    counter = 2
    while candidate.exists():
        candidate = output_dir / f"{slug}-{stamp}-{counter}"
        counter += 1
    return candidate
