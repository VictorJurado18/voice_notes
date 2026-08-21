from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from record_transcript_resume.gui import RecorderApp, _diarization_enabled_by_default


class _Thread:
    def __init__(self, alive: bool) -> None:
        self._alive = alive

    def is_alive(self) -> bool:
        return self._alive


def _app_with_pipeline_running() -> SimpleNamespace:
    app = SimpleNamespace(
        _service=None,
        _stop_thread=None,
        _pipeline_thread=_Thread(True),
        status=Mock(),
        _hide_to_tray=Mock(),
        _tray=SimpleNamespace(notify=Mock(), stop=Mock()),
        destroy=Mock(),
    )
    app._active_work_description = lambda: RecorderApp._active_work_description(app)
    return app


def test_active_work_identifies_pipeline() -> None:
    app = _app_with_pipeline_running()

    assert RecorderApp._active_work_description(app) == "transcrição ou resumo"


def test_close_hides_widget_without_interrupting_pipeline() -> None:
    app = _app_with_pipeline_running()

    RecorderApp._on_close(app)

    app._hide_to_tray.assert_called_once()
    app._tray.notify.assert_called_once()
    app._tray.stop.assert_not_called()
    app.destroy.assert_not_called()


def test_saved_huggingface_token_enables_speaker_separation_by_default() -> None:
    assert _diarization_enabled_by_default("hf_example") is True
    assert _diarization_enabled_by_default("  ") is False
