from pathlib import Path
from unittest.mock import patch

import pytest

from record_transcript_resume.exports import create_pdf_preview
from record_transcript_resume.gui import RecorderApp
from record_transcript_resume.library import BrowserEntry
from datetime import datetime


def test_previews_are_unique_and_preserve_source(tmp_path: Path):
    source = tmp_path / "summary.md"
    source.write_text("# Planejamento\nRevisão das entregas.", encoding="utf-8")
    with patch("record_transcript_resume.exports.tempfile.gettempdir", return_value=str(tmp_path)):
        first, second = create_pdf_preview(source), create_pdf_preview(source)
    assert first != second
    assert first.read_bytes().startswith(b"%PDF")
    assert second.read_bytes().startswith(b"%PDF")
    assert source.read_text(encoding="utf-8").startswith("# Planejamento")


def test_preview_can_use_unsaved_editor_content(tmp_path: Path):
    with patch("record_transcript_resume.exports.tempfile.gettempdir", return_value=str(tmp_path)):
        preview = create_pdf_preview(tmp_path / "unsaved.md", content="# Rascunho\nÚltima alteração.")
    assert preview.is_file()
    assert not (tmp_path / "unsaved.md").exists()


def test_failed_render_cleans_only_its_own_directory(tmp_path: Path):
    unrelated = tmp_path / "VoiceNotes" / "pdf-previews" / "meus-arquivos"
    unrelated.mkdir(parents=True)
    (unrelated / "keep.pdf").write_bytes(b"keep")
    with patch("record_transcript_resume.exports.tempfile.gettempdir", return_value=str(tmp_path)):
        with patch("record_transcript_resume.exports.export_pdf", side_effect=OSError("disk")):
            with pytest.raises(OSError):
                create_pdf_preview(tmp_path / "summary.md", content="# Resumo")
    assert list(unrelated.parent.iterdir()) == [unrelated]


def test_folder_pdf_prefers_valid_summary_then_transcript(tmp_path: Path):
    transcript = tmp_path / "transcription.md"
    summary = tmp_path / "summary.md"
    transcript.write_text("# Transcrição", encoding="utf-8")
    entry = BrowserEntry(tmp_path, "text_record", "Reunião", "Documentos", datetime.now())
    assert RecorderApp._browser_pdf_source(entry) == transcript
    summary.write_text("# Resumo", encoding="utf-8")
    assert RecorderApp._browser_pdf_source(entry) == summary
    summary.write_text("# Summary unavailable", encoding="utf-8")
    assert RecorderApp._browser_pdf_source(entry) == transcript
