from __future__ import annotations

from datetime import datetime

from record_transcript_resume.batch_processing import browser_requests, has_saved_results
from record_transcript_resume.jobs import JobStore, QueueRequest
from record_transcript_resume.library import BrowserEntry


def entry(path, kind):
    return BrowserEntry(path, kind, path.name, "", datetime.now())


def test_batch_selection_follows_visual_order_and_avoids_duplicates(tmp_path):
    a, b = tmp_path / "a.wav", tmp_path / "b.mp3"
    for path in (a, b):
        path.write_bytes(b"audio")
    requests, skipped = browser_requests([entry(b, "audio"), entry(a, "audio"), entry(b, "audio")], tmp_path)
    assert [item.audio for item in requests] == [b, a]
    assert not any(item.reuse_source_folder for item in requests)
    assert skipped == 0


def test_folder_batch_only_selects_immediate_audio_and_ignores_documents(tmp_path):
    folder = tmp_path / "meeting"
    nested = folder / "nested"
    nested.mkdir(parents=True)
    (nested / "hidden.wav").write_bytes(b"audio")
    audio = folder / "meeting.wav"
    audio.write_bytes(b"audio")
    doc = folder / "transcription.md"
    doc.write_text("Text", encoding="utf-8")
    requests, skipped = browser_requests([entry(folder, "recording"), entry(doc, "document")], tmp_path)
    assert [item.audio for item in requests] == [audio]
    assert requests[0].reuse_source_folder
    assert skipped == 1


def test_missing_or_empty_folders_are_skipped(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    requests, skipped = browser_requests([entry(empty, "folder"), entry(tmp_path / "missing", "folder")], tmp_path)
    assert requests == [] and skipped == 2


def test_processed_dedicated_folder_is_flagged_for_explicit_reprocessing(tmp_path):
    folder = tmp_path / "meeting"
    folder.mkdir()
    audio = folder / "meeting.wav"
    audio.write_bytes(b"audio")
    (folder / "transcription.md").write_text("Text", encoding="utf-8")
    assert has_saved_results(QueueRequest(audio, folder, reuse_source_folder=True))
    assert not has_saved_results(QueueRequest(audio, folder, preserve_source=True))
    assert not has_saved_results(QueueRequest(audio, tmp_path))


def test_batch_enqueues_atomically_and_skips_existing_active_jobs(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "jobs.json")
    one, two = tmp_path / "one.wav", tmp_path / "two.wav"
    options = dict(language="pt", model_size="small", provider="codex", summary_template="meeting")
    store.enqueue(one, tmp_path, **options)
    original = store._save
    saves = []
    def save(jobs):
        saves.append(len(jobs))
        original(jobs)
    monkeypatch.setattr(store, "_save", save)
    added = store.enqueue_many([QueueRequest(one, tmp_path), QueueRequest(two, tmp_path), QueueRequest(two, tmp_path)], **options)
    assert saves == [2]
    assert [job.audio_path for job in added] == [two.resolve()]
    assert [job.audio_path for job in store.list()] == [one.resolve(), two.resolve()]


def test_batch_duration_update_does_not_overwrite_measured_duration(tmp_path):
    store = JobStore(tmp_path / "jobs.json")
    job = store.enqueue(tmp_path / "one.wav", tmp_path, "pt", "small", "codex", "meeting")
    store.update_durations({job.id: 120})
    store.update_durations({job.id: 90})
    assert store.list()[0].audio_seconds == 120
