from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor

from record_transcript_resume import gui
from record_transcript_resume.gui import RecorderApp
from record_transcript_resume.jobs import JobStore
from record_transcript_resume.recording import RecordingState


def test_success_cleanup_preserves_files_warnings_and_active_jobs(tmp_path: Path):
    store = JobStore(tmp_path / "jobs.json")
    jobs = []
    for index, status in enumerate(("completed", "warning", "running", "queued")):
        audio = tmp_path / f"{index}.mp3"
        audio.write_bytes(b"fixture")
        job = store.enqueue(audio, tmp_path, "pt", "small", "codex", "meeting")
        store.update(job.id, status=status)
        jobs.append(audio)
    assert store.clear_completed() == 1
    assert {job.status for job in store.list()} == {"warning", "running", "queued"}
    assert all(audio.exists() for audio in jobs)


def test_queue_updates_and_cleanup_do_not_lose_other_jobs(tmp_path: Path):
    store = JobStore(tmp_path / "jobs.json")
    def enqueue(index):
        return store.enqueue(tmp_path / f"{index}.mp3", tmp_path, "pt", "small", "codex", "meeting")
    with ThreadPoolExecutor(max_workers=4) as workers:
        jobs = list(workers.map(enqueue, range(30)))
    assert len(store.list()) == 30
    with ThreadPoolExecutor(max_workers=4) as workers:
        list(workers.map(lambda j:store.update(j.id, status="completed"), jobs))
    assert store.clear_completed() == 30


def test_processing_status_does_not_replace_live_recording_status():
    app = SimpleNamespace(_service=SimpleNamespace(state=RecordingState.RECORDING), _stop_thread=None,
                          status=Mock(), _processing_activity="")
    RecorderApp._set_processing_status(app, "Transcrevendo áudio")
    app.status.set.assert_not_called()
    assert app._processing_status_text == "Transcrevendo áudio"
    assert app._processing_activity == "Transcrevendo áudio"


def test_current_capture_cannot_be_processed(monkeypatch, tmp_path: Path):
    path = tmp_path / "recording.mp3"
    path.write_bytes(b"still being written")
    app = SimpleNamespace(_browser_delete_pending=None, _service=SimpleNamespace(
        state=RecordingState.RECORDING, current_output_path=path), _stop_thread=None)
    app._capture_in_progress = lambda:RecorderApp._capture_in_progress(app)
    app._audio_is_being_written = lambda p:RecorderApp._audio_is_being_written(app, p)
    show = Mock()
    monkeypatch.setattr(gui.messagebox, "showinfo", show)
    assert RecorderApp._queue_pipeline(app, path, "pt", "small", "codex", "meeting") is False
    show.assert_called_once()


def test_low_memory_holds_processing_without_stopping_capture(monkeypatch, tmp_path: Path):
    store = JobStore(tmp_path / "jobs.json")
    job = store.enqueue(tmp_path / "old.mp3", tmp_path, "pt", "large-v3", "codex", "meeting")
    app = SimpleNamespace(_queue_retry_after=None, _active_job_id=None, _pipeline_thread=None,
                          _job_store=store, _audio_is_being_written=lambda p:False,
                          _capture_in_progress=lambda:True, _refresh_processing_page=Mock(),
                          _start_queued_job=Mock(), after=Mock(return_value="retry"), _run_next_pending_job=Mock())
    monkeypatch.setattr(gui, "memory_headroom", lambda:100*1024*1024)
    RecorderApp._run_next_pending_job(app)
    app._start_queued_job.assert_not_called()
    assert store.list()[0].status == "queued"
    assert "proteger" in store.list()[0].stage
    assert app._queue_retry_after == "retry"


def test_queue_waits_for_result_callback_even_after_worker_exits():
    app = SimpleNamespace(_queue_retry_after=None, _active_job_id="finishing-job", _pipeline_thread=None,
                          _job_store=SimpleNamespace(list=Mock()))
    RecorderApp._run_next_pending_job(app)
    app._job_store.list.assert_not_called()
