from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import Mock

from record_transcript_resume.gui import RecorderApp


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
        _service=SimpleNamespace(silence_seconds=600.1),
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
