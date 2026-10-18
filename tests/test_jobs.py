from __future__ import annotations

from pathlib import Path

from record_transcript_resume.jobs import JobStore


def test_job_store_persists_and_recovers_existing_audio(tmp_path: Path) -> None:
    mp3 = tmp_path / "recording.mp3"
    mp3.write_bytes(b"audio")
    store = JobStore(tmp_path / "jobs.json")
    job = store.enqueue(mp3, tmp_path, "pt", "small", "codex", "meeting")
    store.update(job.id, status="running", stage="Transcrevendo")

    recovered = store.recoverable()

    assert len(recovered) == 1
    assert recovered[0].id == job.id
    assert recovered[0].status == "queued"
    assert "Retomando" in recovered[0].stage


def test_job_store_does_not_restart_audio_already_moved(tmp_path: Path) -> None:
    mp3 = tmp_path / "recording.mp3"
    mp3.write_bytes(b"audio")
    store = JobStore(tmp_path / "jobs.json")
    job = store.enqueue(mp3, tmp_path, "pt", "small", "codex", "meeting")
    mp3.unlink()

    assert store.recoverable() == []
    saved = store.list()[0]
    assert saved.id == job.id
    assert saved.status == "needs_attention"


def test_job_store_preserves_meeting_specific_instructions(tmp_path: Path) -> None:
    mp3 = tmp_path / "recording.mp3"
    mp3.write_bytes(b"audio")
    store = JobStore(tmp_path / "jobs.json")

    job = store.enqueue(
        mp3, tmp_path, "pt", "small", "codex", "meeting",
        additional_instructions="Liste riscos e responsáveis.",
    )

    persisted = store.list()[0]
    assert persisted.id == job.id
    assert persisted.additional_instructions == "Liste riscos e responsáveis."


def test_job_store_snapshots_speaker_choice(tmp_path: Path) -> None:
    mp3 = tmp_path / "recording.mp3"
    mp3.write_bytes(b"audio")
    store = JobStore(tmp_path / "jobs.json")

    store.enqueue(mp3, tmp_path, "pt", "small", "codex", "meeting", separate_speakers=True)

    assert store.list()[0].separate_speakers is True


def test_job_store_remembers_that_recording_already_has_its_own_folder(tmp_path: Path) -> None:
    folder = tmp_path / "recording-20261016-120000"
    folder.mkdir()
    audio = folder / f"{folder.name}.mp3"
    audio.write_bytes(b"audio")
    store = JobStore(tmp_path / "jobs.json")

    store.enqueue(
        audio, folder, "pt", "small", "codex", "meeting",
        reuse_source_folder=True,
    )

    assert store.list()[0].reuse_source_folder is True


def test_removing_failed_process_keeps_audio_and_documents(tmp_path: Path) -> None:
    audio = tmp_path / "recording.mp3"
    transcript = tmp_path / "transcription.md"
    audio.write_bytes(b"audio")
    transcript.write_text("# Transcrição", encoding="utf-8")
    store = JobStore(tmp_path / "jobs.json")
    job = store.enqueue(audio, tmp_path, "pt", "small", "codex", "meeting")
    store.update(job.id, status="failed", stage="Transcrevendo", error="Falha de teste")

    assert store.remove(job.id) is True
    assert store.list() == []
    assert audio.read_bytes() == b"audio"
    assert transcript.read_text(encoding="utf-8") == "# Transcrição"
