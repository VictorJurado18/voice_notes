from __future__ import annotations

from datetime import datetime
from pathlib import Path

from record_transcript_resume.library import LibraryMetadataStore, discover_recordings


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
    assert items[0].contents_label == "Só Resumo"
    assert items[0].next_step_label == "Pronto para consultar"
    assert items[1].title == "Older"


def test_discover_recordings_includes_summary_failure_for_recovery(tmp_path: Path) -> None:
    folder = tmp_path / "failed-summary"
    folder.mkdir()
    (folder / "transcription.md").write_text("# Transcription\n\nText", encoding="utf-8")
    (folder / "summary.md").write_text("# Summary unavailable\n\nRetry", encoding="utf-8")

    item = discover_recordings(tmp_path)[0]

    assert item.summary_available is False
    assert item.transcript_path is not None
    assert item.contents_label == "Só Transcrição"
    assert item.next_step_label == "Resumo com falha · tente gerar novamente"


def test_discover_recordings_includes_audio_saved_before_processing(tmp_path: Path) -> None:
    audio = tmp_path / "recording-20260825-101500.mp3"
    audio.write_bytes(b"saved-audio")

    item = discover_recordings(tmp_path)[0]

    assert item.mp3_path == audio
    assert item.transcript_path is None
    assert item.summary_path is None
    assert item.title == "Gravação de 25/08 às 10:15"
    assert item.has_own_folder is False
    assert item.recorded_at == datetime(2026, 8, 25, 10, 15)
    assert item.sort_at == item.recorded_at
    assert item.contents_label == "Só Áudio"
    assert item.next_step_label == "Pronto para transcrever"


def test_recording_date_stays_stable_after_processing_changes_folder(tmp_path: Path) -> None:
    folder = tmp_path / "recording-20261014-094211"
    folder.mkdir()
    audio = folder / f"{folder.name}.mp3"
    audio.write_bytes(b"audio")
    (folder / "transcription.md").write_text("# Transcription\n\nText", encoding="utf-8")

    item = discover_recordings(tmp_path)[0]

    assert item.sort_at == datetime(2026, 10, 14, 9, 42, 11)
    assert item.modified_at != item.sort_at


def test_discover_recordings_accepts_a_single_recording_folder(tmp_path: Path) -> None:
    folder = tmp_path / "meeting"
    folder.mkdir()
    audio = folder / "meeting.mp3"
    audio.write_bytes(b"audio")
    (folder / "transcription.md").write_text("# Transcription\n\nHello", encoding="utf-8")

    items = discover_recordings(folder)

    assert len(items) == 1
    assert items[0].folder == folder
    assert items[0].mp3_path == audio
    assert items[0].transcript_path == folder / "transcription.md"
    assert items[0].has_own_folder is True


def test_discover_recordings_keeps_older_nested_results_visible(tmp_path: Path) -> None:
    outer = tmp_path / "senappen"
    outer.mkdir()
    (outer / "transcription.md").write_text("# Transcription\n\nNotes", encoding="utf-8")
    inner = outer / "recording-recording-20261014-100227"
    inner.mkdir()
    audio = inner / "recording-20261014-100227.mp3"
    audio.write_bytes(b"audio")
    (inner / "transcription.md").write_text("# Transcription\n\nMeeting", encoding="utf-8")

    items = discover_recordings(tmp_path)

    assert {item.folder for item in items} == {outer, inner}
    recorded = next(item for item in items if item.mp3_path == audio)
    assert recorded.title == "Gravação de 14/10 às 10:02"
    assert recorded.has_own_folder is True
    assert recorded.nested_in == "senappen"
    assert recorded.contents_label == "Áudio + Transcrição"
    assert recorded.next_step_label == "Pronto para gerar resumo"


def test_metadata_transfer_to_same_audio_preserves_organization(tmp_path: Path) -> None:
    audio = tmp_path / "recording.mp3"
    audio.write_bytes(b"audio")
    store = LibraryMetadataStore(tmp_path / "metadata.json")
    store.save(audio, title="Reunião", tags=("cliente",), favorite=True)

    store.transfer(audio, audio)

    item = discover_recordings(tmp_path, store)[0]
    assert (item.title, item.tags, item.favorite) == ("Reunião", ("cliente",), True)


def test_discover_recordings_finds_imported_wav_and_user_organization(tmp_path: Path) -> None:
    folder = tmp_path / "imported"
    folder.mkdir()
    audio = folder / "meeting.WAV"
    audio.write_bytes(b"fixture")
    (folder / "transcription.md").write_text("# Transcription\n\nText", encoding="utf-8")
    store = LibraryMetadataStore(tmp_path / "metadata.json")
    store.save(audio, title="Reunião da equipe", tags=("cliente", "prioridade"), favorite=True)

    item = discover_recordings(tmp_path, store)[0]

    assert item.mp3_path == audio
    assert item.title == "Reunião da equipe"
    assert item.tags == ("cliente", "prioridade")
    assert item.favorite is True
    assert "cliente" in item.searchable_text


def test_favorite_change_keeps_user_title_and_tags(tmp_path: Path) -> None:
    audio = tmp_path / "meeting.m4a"
    audio.write_bytes(b"fixture")
    store = LibraryMetadataStore(tmp_path / "metadata.json")
    store.save(audio, title="Meu título", tags=("trabalho",), favorite=False)
    store.save(audio, favorite=True)

    item = discover_recordings(tmp_path, store)[0]
    assert (item.title, item.tags, item.favorite) == ("Meu título", ("trabalho",), True)


def test_organization_follows_recording_into_result_folder(tmp_path: Path) -> None:
    audio = tmp_path / "recording.mp3"
    audio.write_bytes(b"fixture")
    folder = tmp_path / "result"
    folder.mkdir()
    moved_audio = folder / audio.name
    moved_audio.write_bytes(b"fixture")
    audio.unlink()
    store = LibraryMetadataStore(tmp_path / "metadata.json")
    store.save(audio, title="Nome pessoal", favorite=True)
    store.transfer(audio, moved_audio)

    item = discover_recordings(tmp_path, store)[0]
    assert item.title == "Nome pessoal"
    assert item.favorite is True
