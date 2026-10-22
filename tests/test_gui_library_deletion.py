from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import pytest

from record_transcript_resume import gui
from record_transcript_resume.gui import RecorderApp
from record_transcript_resume.library import BrowserEntry
from record_transcript_resume.recording import RecordingState


@pytest.fixture
def deletion(tmp_path: Path, monkeypatch):
    root = tmp_path / "library"
    folder = root / "recording-test"
    folder.mkdir(parents=True)
    audio = folder / "audio.mp3"
    audio.write_bytes(b"synthetic audio")
    entry = BrowserEntry(folder, "recording", "Gravação de teste", "Áudio", datetime.now())
    app = SimpleNamespace(
        _browser_selected=entry, _browser_directory=root, _browser_delete_pending=None,
        library_dir=SimpleNamespace(get=lambda: str(root)),
        output_dir=SimpleNamespace(get=lambda: str(root)),
        _service=None, _stop_thread=None, _summary_source_path=None,
        _youtube_download_thread=None, _job_store=SimpleNamespace(list=Mock(return_value=[])),
        _editor_document_path=None, _browser_audio_path=None, _last_output=audio,
        _browser_history=[root, root / "missing"], status=Mock(),
        _close_transcript_editor=Mock(return_value=True), _close_browser_audio=Mock(),
        _browser_update_folder_actions=Mock(), _browser_delete_worker=Mock(),
        _post_to_ui=Mock(), _on_browser_delete_done=Mock(),
        _refresh_library=Mock(), _browser_select=Mock(), retry_summary_button=Mock(),
    )
    app._browser_delete_busy_reason = MethodType(RecorderApp._browser_delete_busy_reason, app)
    app._selected_browser_entries = MethodType(RecorderApp._selected_browser_entries, app)
    thread = Mock()
    constructor = Mock(return_value=thread)
    monkeypatch.setattr(gui.threading, "Thread", constructor)
    monkeypatch.setattr(gui.messagebox, "askyesno", Mock(return_value=True))
    monkeypatch.setattr(gui.messagebox, "showinfo", Mock())
    monkeypatch.setattr(gui.messagebox, "showerror", Mock())
    return app, root, folder, audio, constructor, thread


def test_no_selection_never_falls_back_to_deleting_the_current_folder(deletion) -> None:
    app, root, folder, audio, constructor, thread = deletion
    app._browser_selected = None

    assert RecorderApp._browser_delete(app) == "break"

    gui.messagebox.askyesno.assert_not_called()
    constructor.assert_not_called()
    assert root.is_dir() and audio.is_file()


def test_cancelling_confirmation_changes_nothing(deletion) -> None:
    app, root, folder, audio, constructor, thread = deletion
    gui.messagebox.askyesno.return_value = False

    RecorderApp._browser_delete(app)

    constructor.assert_not_called()
    app._close_browser_audio.assert_not_called()
    assert app._browser_delete_pending is None
    assert audio.is_file()


def test_folder_confirmation_is_explicit_and_defaults_to_no(deletion) -> None:
    app, root, folder, audio, constructor, thread = deletion
    app._browser_audio_path = audio

    RecorderApp._browser_delete(app)

    prompt = gui.messagebox.askyesno.call_args
    assert str(folder.resolve()) in prompt.args[1]
    assert "pasta inteira" in prompt.args[1] and "subpastas" in prompt.args[1]
    assert prompt.kwargs["default"] == gui.messagebox.NO
    assert app._browser_delete_pending == folder.resolve()
    app._close_browser_audio.assert_called_once()
    assert constructor.call_args.kwargs["args"][:2] == (root, folder.resolve())
    thread.start.assert_called_once()


def test_selecting_a_file_never_escalates_to_its_recording_folder(deletion) -> None:
    app, root, folder, audio, constructor, thread = deletion
    app._browser_directory = folder
    app._browser_selected = BrowserEntry(audio, "audio", audio.name, "MP3", datetime.now())

    RecorderApp._browser_delete(app)

    assert app._browser_delete_pending == audio.resolve()
    assert constructor.call_args.kwargs["args"][:2] == (folder, audio.resolve())
    assert "Este arquivo" in gui.messagebox.askyesno.call_args.args[1]
    assert "pasta inteira" not in gui.messagebox.askyesno.call_args.args[1]


@pytest.mark.parametrize("state", [RecordingState.RECORDING, RecordingState.FINALIZING])
def test_active_recording_and_finalization_block_deletion(deletion, state) -> None:
    app, root, folder, audio, constructor, thread = deletion
    app._service = SimpleNamespace(state=state, current_output_path=audio)

    RecorderApp._browser_delete(app)

    gui.messagebox.askyesno.assert_not_called()
    gui.messagebox.showinfo.assert_called_once()
    constructor.assert_not_called()


@pytest.mark.parametrize("state", ["queued", "running"])
def test_active_queue_jobs_block_deletion(deletion, state: str) -> None:
    app, root, folder, audio, constructor, thread = deletion
    app._job_store.list.return_value = [SimpleNamespace(status=state, mp3_path=str(audio), output_dir=str(folder))]

    RecorderApp._browser_delete(app)

    gui.messagebox.askyesno.assert_not_called()
    constructor.assert_not_called()


def test_job_started_while_confirmation_was_open_is_checked_again(deletion) -> None:
    app, root, folder, audio, constructor, thread = deletion
    job = SimpleNamespace(status="running", mp3_path=str(audio), output_dir=str(folder))
    app._job_store.list.side_effect = [[], [job]]

    RecorderApp._browser_delete(app)

    gui.messagebox.askyesno.assert_called_once()
    gui.messagebox.showinfo.assert_called_once()
    constructor.assert_not_called()


def test_summary_regeneration_protects_the_recording_folder(deletion) -> None:
    app, root, folder, audio, constructor, thread = deletion
    app._summary_source_path = folder / "transcription.md"

    RecorderApp._browser_delete(app)

    gui.messagebox.askyesno.assert_not_called()
    constructor.assert_not_called()


def test_library_root_remains_protected_after_navigating_up(deletion) -> None:
    app, root, folder, audio, constructor, thread = deletion
    app._browser_directory = root.parent
    app._browser_selected = BrowserEntry(root, "folder", "library", "", datetime.now())

    RecorderApp._browser_delete(app)

    gui.messagebox.askyesno.assert_not_called()
    gui.messagebox.showerror.assert_called_once()
    constructor.assert_not_called()


def test_unsaved_editor_can_cancel_the_operation(deletion) -> None:
    app, root, folder, audio, constructor, thread = deletion
    app._editor_document_path = folder / "transcription.md"
    app._close_transcript_editor.return_value = False

    RecorderApp._browser_delete(app)

    app._close_transcript_editor.assert_called_once()
    constructor.assert_not_called()


@pytest.mark.parametrize("error", [None, "file is locked"])
def test_worker_posts_completion_to_the_ui_queue(deletion, monkeypatch, error: str | None) -> None:
    app, root, folder, audio, constructor, thread = deletion
    recycle = Mock(side_effect=OSError(error) if error else None)
    monkeypatch.setattr(gui, "recycle_library_entry", recycle)

    RecorderApp._browser_delete_worker(app, root, folder, (root,))

    recycle.assert_called_once_with(root, folder, protected_roots=(root,))
    app._post_to_ui.assert_called_once_with(app._on_browser_delete_done, folder, error)


def test_success_refreshes_library_and_clears_only_the_deleted_selection(deletion) -> None:
    app, root, folder, audio, constructor, thread = deletion
    app._browser_delete_pending = folder

    RecorderApp._on_browser_delete_done(app, folder, None)

    assert app._browser_delete_pending is None
    assert app._browser_selected is None
    assert app._last_output is None
    assert app._browser_history == [root]
    app._refresh_library.assert_called_once()
    app.retry_summary_button.configure.assert_called_once_with(state=gui.tk.DISABLED)
    gui.messagebox.showerror.assert_not_called()


def test_error_preserves_selection_and_reports_failure(deletion) -> None:
    app, root, folder, audio, constructor, thread = deletion
    original = app._browser_selected
    app._browser_delete_pending = folder

    RecorderApp._on_browser_delete_done(app, folder, "file is locked")

    assert app._browser_delete_pending is None
    assert app._browser_selected is original
    assert app._last_output == audio
    app._refresh_library.assert_called_once()
    app._browser_select.assert_called_once()
    gui.messagebox.showerror.assert_called_once()
