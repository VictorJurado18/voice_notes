from __future__ import annotations

import pytest

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
