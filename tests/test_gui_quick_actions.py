from __future__ import annotations

from pathlib import Path
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
    )
    monkeypatch.setattr(gui.filedialog, "askopenfilename", choose_file)

    RecorderApp._process_existing_media(app)

    assert chooser["title"] == "Importar áudio ou vídeo para transcrever"
    assert "*.mp4" in " ".join(pattern for _label, pattern in chooser["filetypes"])
    app._queue_pipeline.assert_called_once_with(
        video, "en", "medium", "api:provider-a", "interview",
        transcription_provider="local", separate_speakers=False,
    )


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


def test_processing_feedback_is_inserted_before_the_active_page_content() -> None:
    anchor = object()
    progressbar = Mock()
    actions = Mock()
    app = SimpleNamespace(
        _current_page="file",
        _page_layouts={"file": [(anchor, {})]},
        progressbar=progressbar,
        _processing_actions=actions,
    )

    RecorderApp._pack_global_processing_feedback(app)

    progressbar.pack.assert_called_once_with(fill=gui.tk.X, padx=20, pady=(4, 0), before=anchor)
    actions.pack.assert_called_once_with(fill=gui.tk.X, padx=20, pady=(7, 0), before=anchor)
