from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from record_transcript_resume.gui import RecorderApp
from record_transcript_resume.recording import RecordingState


def test_recording_timer_accepts_minutes_and_hours() -> None:
    assert RecorderApp._recording_timer_seconds("2.5", "minutos") == 150
    assert RecorderApp._recording_timer_seconds("1,5", "horas") == 5400
    assert RecorderApp._recording_timer_seconds("", "minutos") == 0


@pytest.mark.parametrize("value", ["zero", "0", "-1"])
def test_recording_timer_rejects_invalid_or_non_positive_values(value: str) -> None:
    with pytest.raises(ValueError):
        RecorderApp._recording_timer_seconds(value, "minutos")


def test_recording_timer_formats_short_and_long_durations() -> None:
    assert RecorderApp._format_duration(75) == "01:15"
    assert RecorderApp._format_duration(3661) == "01:01:01"


def test_silence_timeout_requests_one_automatic_stop() -> None:
    callbacks = []
    fake = SimpleNamespace(
        _recording_silence_seconds=600,
        _recording_deadline=None,
        _service=SimpleNamespace(state=RecordingState.RECORDING, silence_seconds=600.1),
        recording_limit_hint=Mock(),
        _format_duration=RecorderApp._format_duration,
        after_idle=callbacks.append,
        _stop_recording=Mock(),
    )

    RecorderApp._check_silence_timeout(fake)
    RecorderApp._check_silence_timeout(fake)

    assert len(callbacks) == 1
    callbacks[0]()
    fake._stop_recording.assert_called_once_with(automatic=True, silence=True)


def test_silence_timeout_does_not_stop_while_paused() -> None:
    callbacks = []
    fake = SimpleNamespace(
        _recording_silence_seconds=600,
        _recording_deadline=None,
        _service=SimpleNamespace(state=RecordingState.PAUSED, silence_seconds=700),
        after_idle=callbacks.append,
    )

    RecorderApp._check_silence_timeout(fake)

    assert fake._recording_silence_seconds == 600
    assert callbacks == []


def test_pause_resume_shifts_duration_limit_without_changing_output() -> None:
    service = SimpleNamespace(state=RecordingState.RECORDING, current_output_path="same.mp3")
    def pause(): service.state = RecordingState.PAUSED
    def resume(): service.state = RecordingState.RECORDING
    service.pause = pause
    service.resume = resume
    button = Mock()
    fake = SimpleNamespace(
        _service=service, _stop_thread=None, _started_at=50.0,
        _paused_at=None, _recording_deadline=200.0,
        status=Mock(), pause_button=button, inline_pause_button=button,
        _focus_pause_button=button, _tray=Mock(),
        _sync_recording_meter=Mock(), _refresh_compact_controls=Mock(),
    )

    with patch("record_transcript_resume.gui.time.monotonic", side_effect=[100.0, 130.0]):
        RecorderApp._toggle_pause_recording(fake)
        assert fake._paused_at == 100.0
        assert fake._started_at == 50.0
        assert fake._recording_deadline == 200.0
        RecorderApp._toggle_pause_recording(fake)

    assert service.current_output_path == "same.mp3"
    assert fake._paused_at is None
    assert fake._started_at == 80.0
    assert fake._recording_deadline == 230.0
    button.configure.assert_called_with(text="Pausar")
