from __future__ import annotations

from pathlib import Path
from queue import SimpleQueue
from types import SimpleNamespace
from unittest.mock import Mock

from record_transcript_resume import exports, gui
from record_transcript_resume.api_provider import ApiProviderConfig
from record_transcript_resume.gui import RecorderApp


class _Value:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class _BoolValue:
    def __init__(self, value: bool) -> None:
        self.value = value

    def get(self) -> bool:
        return self.value


def test_pipeline_steps_match_transcription_only_flow() -> None:
    app = SimpleNamespace(
        _pipeline_output_mode="transcription",
        _pipeline_has_speaker_separation=False,
        _pipeline_total_steps=RecorderApp._pipeline_total_steps,
    )
    assert RecorderApp._pipeline_total_steps("transcription", False) == 2
    assert RecorderApp._pipeline_stage_label(app, "Transcribing audio...") == "1/2 · Transcrevendo áudio"
    assert RecorderApp._pipeline_total_steps("both", True) == 4


def test_copy_open_document_copies_all_editor_content() -> None:
    app = SimpleNamespace(
        _library_editing=True,
        transcript_editor=SimpleNamespace(get=Mock(return_value="# Resumo\n\nConteúdo completo")),
        clipboard_clear=Mock(),
        clipboard_append=Mock(),
        update=Mock(),
        status=Mock(),
    )

    RecorderApp._copy_open_document(app)

    app.clipboard_clear.assert_called_once()
    app.clipboard_append.assert_called_once_with("# Resumo\n\nConteúdo completo")
    app.update.assert_called_once()
    app.status.set.assert_called_once_with("Texto completo copiado para a área de transferência.")


def test_exported_pdf_is_opened_after_success(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "summary.md"
    destination = tmp_path / "resumo.pdf"
    item = SimpleNamespace(summary_path=source, transcript_path=None, title="Reunião")
    app = SimpleNamespace(
        _selected_library_item=lambda: item,
        _library_editing=False,
        _editor_document_path=None,
        status=Mock(),
    )
    opened: list[str] = []
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **_kwargs: str(destination))
    monkeypatch.setattr(exports, "export_pdf", lambda _source, _destination: destination)
    monkeypatch.setattr(gui.os, "startfile", lambda path: opened.append(path))

    RecorderApp._export_selected_document(app, "pdf")

    assert opened == [str(destination)]
    app.status.set.assert_called_once_with("PDF exportado e aberto: resumo.pdf")


def test_media_import_uses_the_visible_file_configuration(monkeypatch, tmp_path: Path) -> None:
    video = tmp_path / "reuniao.mp4"
    chooser: dict[str, object] = {}

    def choose_file(**kwargs: object) -> str:
        chooser.update(kwargs)
        return str(video)

    app = SimpleNamespace(
        output_dir=_Value(str(tmp_path)),
        file_pipeline_language=_Value("English"),
        file_pipeline_model=_Value("medium"),
        file_summary_provider=_Value("API · Equipe A"),
        file_processing_profile=_Value("Entrevista"),
        file_transcription_source=_Value("Whisper local"),
        file_diarize_speakers=_BoolValue(False),
        _summary_provider_code_for_label=lambda label: "api:provider-a" if label == "API · Equipe A" else "codex",
        _summary_template_code_for_choice=lambda profile, template: "interview" if profile == "Entrevista" else "meeting",
        _transcription_provider_code_for_label=lambda _label: "local",
        _queue_pipeline=Mock(),
        _show_page=Mock(),
    )
    monkeypatch.setattr(gui.filedialog, "askopenfilename", choose_file)

    RecorderApp._process_existing_media(app)

    assert chooser["title"] == "Importar áudio ou vídeo para transcrever"
    assert "*.mp4" in " ".join(pattern for _label, pattern in chooser["filetypes"])
    app._queue_pipeline.assert_called_once_with(
        video, "en", "medium", "api:provider-a", "interview",
        output_dir=tmp_path, transcription_provider="local",
        separate_speakers=False, preserve_source=True,
    )
    app._show_page.assert_called_once_with("processing")


def test_saved_api_provider_is_an_individually_selectable_summary_provider() -> None:
    app = SimpleNamespace(
        _api_provider_configs=[
            ApiProviderConfig(id="provider-a", name="Equipe A", model="modelo-a"),
            ApiProviderConfig(id="provider-b", name="Equipe B", model="modelo-b"),
        ],
        _api_provider_labels={},
        summary_provider=_Value("API · Equipe B"),
    )

    values = RecorderApp._summary_provider_options(app)

    assert "API · Equipe A" in values
    assert "API · Equipe B" in values
    assert RecorderApp._selected_summary_provider_code(app) == "api:provider-b"


def test_resize_defers_responsive_layout_until_drag_ends() -> None:
    app = SimpleNamespace(
        _last_responsive_width=650,
        _last_responsive_height=850,
        _responsive_wrap_after=None,
        _resize_active=True,
        after=Mock(),
        after_cancel=Mock(),
    )
    event = SimpleNamespace(widget=app, width=1300, height=850)

    RecorderApp._schedule_responsive_wraps(app, event)

    assert (app._last_responsive_width, app._last_responsive_height) == (1300, 850)
    app.after.assert_not_called()


def test_desktop_reflow_only_touches_the_selected_page() -> None:
    app = SimpleNamespace(
        _desktop_layout=True,
        _page_layout_desktop={},
        _layout_record_sections=Mock(),
        _layout_source_choices=Mock(),
        _layout_import_actions=Mock(),
        _layout_browser=Mock(),
        _layout_processing_panel=Mock(),
    )

    RecorderApp._ensure_page_layout(app, "library")
    RecorderApp._ensure_page_layout(app, "library")

    app._layout_browser.assert_called_once()
    app._layout_record_sections.assert_not_called()
    app._layout_import_actions.assert_not_called()
    app._layout_processing_panel.assert_not_called()


def test_focus_text_import_replaces_audio_steps() -> None:
    sections = (Mock(), Mock(), Mock())
    panel = Mock()
    app = SimpleNamespace(
        _focus_text_tools_visible=False,
        _focus_file_audio_sections=sections,
        _focus_text_import_panel=panel,
    )

    RecorderApp._focus_show_text_tools(app)

    assert app._focus_text_tools_visible is True
    for section in sections:
        section.pack_forget.assert_called_once()
    panel.pack.assert_called_once()

    RecorderApp._focus_show_text_tools(app)

    assert app._focus_text_tools_visible is False
    panel.pack_forget.assert_called_once()
    for section in sections:
        section.pack.assert_called_once()


def test_text_import_uses_visible_focus_editor() -> None:
    focus_editor = object()
    full_editor = object()
    app = SimpleNamespace(
        _focus_text_tools_visible=True,
        _maximized=False,
        _focus_import_text_editor=focus_editor,
        import_text_editor=full_editor,
    )

    assert RecorderApp._active_import_text_editor(app) is focus_editor
    app._maximized = True
    assert RecorderApp._active_import_text_editor(app) is full_editor


def test_hide_without_tray_temporarily_restores_native_window_management() -> None:
    app = SimpleNamespace(
        _tray_available=False,
        _close_browser_audio=Mock(),
        overrideredirect=Mock(return_value=True),
        iconify=Mock(),
        _restore_borderless_on_map=False,
    )

    RecorderApp._hide_to_tray(app)

    app.overrideredirect.assert_any_call(False)
    app.iconify.assert_called_once()
    assert app._restore_borderless_on_map is True


def test_update_workers_pass_results_without_calling_tk_from_threads(monkeypatch) -> None:
    from record_transcript_resume import updates

    check_result = object()
    download_result = object()
    app = SimpleNamespace(
        _ui_actions=SimpleQueue(),
        _on_update_checked=Mock(),
        _on_update_applied=Mock(),
        after=Mock(),
        winfo_exists=Mock(return_value=True),
    )
    app._post_to_ui = lambda callback, *args: RecorderApp._post_to_ui(app, callback, *args)
    app._drain_ui_actions = lambda: RecorderApp._drain_ui_actions(app)
    monkeypatch.setattr(updates, "check_for_updates", lambda: check_result)
    monkeypatch.setattr(updates, "download_update", lambda _update: download_result)

    RecorderApp._update_check_worker(app)
    RecorderApp._apply_update_worker(app, object())

    app.after.assert_not_called()
    RecorderApp._drain_ui_actions(app)
    app._on_update_checked.assert_called_once_with(check_result)
    app._on_update_applied.assert_called_once_with(download_result)
    app.after.assert_called_once()

    app.after.reset_mock()
    app.winfo_exists.return_value = False
    RecorderApp._drain_ui_actions(app)
    app.after.assert_not_called()


def test_empty_system_recording_explains_that_no_computer_sound_was_captured(tmp_path: Path) -> None:
    app = SimpleNamespace(
        _set_recording_action_state=Mock(),
        device_info_text=Mock(),
        _started_at=None,
        _recording_deadline=None,
        recording_limit_hint=Mock(),
        _sync_recording_meter=Mock(),
        last_file=Mock(),
        mode=_Value("system"),
        _show_stop_error=Mock(),
    )

    RecorderApp._show_completed(app, tmp_path / "empty.mp3")

    message = app._show_stop_error.call_args.args[0]
    assert "Nenhum som do computador foi capturado" in message
