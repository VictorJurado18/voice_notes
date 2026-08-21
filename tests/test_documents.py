from __future__ import annotations

from pathlib import Path

from record_transcript_resume.documents import create_imported_transcript


def test_create_imported_transcript_creates_library_compatible_document(tmp_path: Path) -> None:
    transcript = create_imported_transcript("# Transcrição\n\nTexto corrigido.", tmp_path, "Reunião do time")

    assert transcript.name == "transcription.md"
    assert transcript.parent.parent == tmp_path
    assert transcript.read_text(encoding="utf-8") == "# Transcrição\n\nTexto corrigido.\n"
