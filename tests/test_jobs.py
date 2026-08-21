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
