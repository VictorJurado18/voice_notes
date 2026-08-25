from __future__ import annotations

from pathlib import Path

from record_transcript_resume.library import discover_recordings


def test_discover_recordings_uses_summary_heading_and_sorts_newest(tmp_path: Path) -> None:
    older = tmp_path / "older"
    older.mkdir()
    (older / "transcription.md").write_text("# Transcription\n\nOld text", encoding="utf-8")
    newer = tmp_path / "newer"
    newer.mkdir()
    (newer / "summary.md").write_text("# Planejamento do projeto\n\n## Contexto", encoding="utf-8")

    items = discover_recordings(tmp_path)

    assert [item.folder.name for item in items] == ["newer", "older"]
    assert items[0].title == "Planejamento do projeto"
    assert items[1].title == "Older"


def test_discover_recordings_includes_summary_failure_for_recovery(tmp_path: Path) -> None:
    folder = tmp_path / "failed-summary"
    folder.mkdir()
    (folder / "transcription.md").write_text("# Transcription\n\nText", encoding="utf-8")
    (folder / "summary.md").write_text("# Summary unavailable\n\nRetry", encoding="utf-8")

    item = discover_recordings(tmp_path)[0]

    assert item.summary_available is False
    assert item.transcript_path is not None


def test_discover_recordings_includes_audio_saved_before_processing(tmp_path: Path) -> None:
    audio = tmp_path / "recording-20260825-101500.mp3"
    audio.write_bytes(b"saved-audio")

    item = discover_recordings(tmp_path)[0]

    assert item.mp3_path == audio
    assert item.transcript_path is None
    assert item.summary_path is None
    assert item.title == "Recording 20260825 101500"
