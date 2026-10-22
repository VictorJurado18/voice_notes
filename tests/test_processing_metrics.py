from pathlib import Path
import wave
from record_transcript_resume.processing_metrics import ProcessingMetricsStore, media_duration, profile_key
from record_transcript_resume.resource_policy import transcription_threads, worker_environment


def test_forecast_learns_and_persists_for_matching_configuration(tmp_path: Path):
    key = profile_key("small", "local", "codex", "both", False, 4)
    store = ProcessingMetricsStore(tmp_path / "times.json")
    store.record(key, 600, 300)
    forecast = ProcessingMetricsStore(store.path).estimate(key, 1200)
    assert forecast.samples == 1
    assert forecast.low <= 600 <= forecast.high
    other = store.estimate(profile_key("medium", "local", "codex", "both", False, 4), 1200)
    assert other.samples == 0


def test_short_or_invalid_runs_do_not_train_estimator(tmp_path: Path):
    store = ProcessingMetricsStore(tmp_path / "times.json")
    store.record("key", 1, 3)
    store.record("key", float("nan"), 5)
    store.record("key", 60, -1)
    assert store.estimate("key", 600).samples == 0


def test_corrupt_timings_do_not_break_library(tmp_path: Path):
    path = tmp_path / "times.json"
    path.write_bytes(b"\xffinvalid")
    store = ProcessingMetricsStore(path)
    assert store.estimate("key", 600).samples == 0
    assert store.estimate("key", 0) is None


def test_duration_reads_media_metadata(tmp_path: Path):
    path = tmp_path / "example.wav"
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        output.writeframes(b"\0\0" * 32000)
    assert abs(media_duration(path) - 2) < .01
    assert media_duration(tmp_path / "missing.mp3") == 0


def test_cpu_threads_reserve_capacity(monkeypatch):
    monkeypatch.setattr("record_transcript_resume.resource_policy.os.cpu_count", lambda: 8)
    assert transcription_threads() == 4
    env = worker_environment({"SAVED": "yes", "OMP_NUM_THREADS": "100"})
    assert env["OMP_NUM_THREADS"] == "4" and env["SAVED"] == "yes"
    monkeypatch.setattr("record_transcript_resume.resource_policy.os.cpu_count", lambda: 2)
    assert transcription_threads() == 1
