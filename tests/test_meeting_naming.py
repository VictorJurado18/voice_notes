from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from record_transcript_resume.gui import RecorderApp
from record_transcript_resume.jobs import JobStore
from record_transcript_resume.library import BrowserEntry, LibraryMetadataStore, browse_directory, discover_recordings
from record_transcript_resume.meeting_naming import recording_time, safe_name
from record_transcript_resume.meeting_topics import load_topic
from record_transcript_resume.pipeline import finalize_content_name, run
from record_transcript_resume.synthesis import SynthesisResult, _result_from_stdout
from record_transcript_resume.transcription import Segment


def process(audio, destination, **kwargs):
    response = SynthesisResult("revisao-do-cronograma", "# Cronograma\nEntregas previstas.", "Cronograma das entregas")
    with patch("record_transcript_resume.pipeline.transcribe", return_value=[Segment(0, 2, "Revisão do cronograma.")]), \
         patch("record_transcript_resume.pipeline.generate", return_value=response) as generate:
        result = run(audio, destination, **kwargs)
    if kwargs.get("output_mode") != "transcription":
        generate.assert_called_once()
    else:
        generate.assert_not_called()
    return result


def recording(root):
    folder = root / "recording-20261020-093000"
    folder.mkdir(parents=True)
    audio = folder / (folder.name + ".mp3")
    audio.write_bytes(b"original recording")
    return audio


def test_names_topic_and_original_date_survive_processing(tmp_path):
    audio = recording(tmp_path)
    result = process(audio, audio.parent, reuse_source_folder=True)
    assert result.folder == tmp_path / "revisao-do-cronograma"
    assert result.mp3_path.name == "revisao-do-cronograma.mp3"
    assert result.mp3_path.read_bytes() == b"original recording"
    assert not audio.parent.exists()
    assert load_topic(result.folder) == "Cronograma das entregas"
    assert not result.warnings
    expected = datetime(2026, 10, 20, 9, 30)
    assert recording_time(result.mp3_path) == expected
    metadata = LibraryMetadataStore(tmp_path / "absent.json")
    assert browse_directory(tmp_path, metadata)[0].sort_at == expected
    assert discover_recordings(tmp_path, metadata)[0].sort_at == expected
    assert all(e.path.name != ".voice-notes.json" for e in browse_directory(result.folder, metadata))


def test_collision_uses_matching_folder_and_audio_suffix(tmp_path):
    existing = tmp_path / "revisao-do-cronograma"
    existing.mkdir()
    sentinel = existing / "dont-touch.txt"
    sentinel.write_text("preserve")
    audio = recording(tmp_path)
    result = process(audio, audio.parent, reuse_source_folder=True)
    assert result.folder.name == "revisao-do-cronograma-2"
    assert result.mp3_path.name == "revisao-do-cronograma-2.mp3"
    assert sentinel.read_text() == "preserve"


def test_import_renames_only_library_copy_and_keeps_extension(tmp_path):
    audio = tmp_path / "original.WAV"
    audio.write_bytes(b"original")
    result = process(audio, tmp_path / "library", preserve_source=True)
    assert audio.read_bytes() == b"original"
    assert result.mp3_path.name == "revisao-do-cronograma.WAV"
    assert result.mp3_path.read_bytes() == b"original"
    assert result.previous_folder is None


def test_shared_directory_is_not_renamed_or_overwritten(tmp_path):
    audio = recording(tmp_path)
    other = audio.with_name("another.mp3")
    other.write_bytes(b"other meeting")
    document = audio.with_name("summary.md")
    document.write_text("# Other summary")
    result = process(audio, audio.parent, reuse_source_folder=True)
    assert audio.parent.is_dir()
    assert other.read_bytes() == b"other meeting"
    assert document.read_text() == "# Other summary"
    assert result.folder == audio.parent / "revisao-do-cronograma"
    assert result.previous_folder is None


def test_locked_folder_keeps_successful_outputs_and_valid_paths(tmp_path):
    audio = recording(tmp_path)
    rename = Path.rename
    def locked(path, destination):
        if path == audio.parent:
            raise PermissionError("Folder open in another application")
        return rename(path, destination)
    with patch.object(Path, "rename", locked):
        result = process(audio, audio.parent, reuse_source_folder=True)
    assert result.warnings and not result.summary_failed
    assert result.folder == audio.parent
    assert result.mp3_path == audio
    assert result.mp3_path.is_file() and result.transcript_path.is_file() and result.summary_path.is_file()
    assert result.previous_folder is None
    assert load_topic(result.folder) == "Cronograma das entregas"


def test_transcription_only_keeps_names_without_calling_summary_provider(tmp_path):
    audio = recording(tmp_path)
    result = process(audio, audio.parent, reuse_source_folder=True, output_mode="transcription")
    assert result.mp3_path == audio and result.folder == audio.parent
    assert result.summary_path is None


def test_worker_defers_renaming_until_gui_has_received_success(tmp_path):
    audio = recording(tmp_path)
    saved = process(audio, audio.parent, reuse_source_folder=True, defer_content_name=True)
    assert saved.mp3_path == audio and audio.is_file()
    assert saved.content_name == "revisao-do-cronograma"
    result = finalize_content_name(saved)
    assert result.mp3_path.is_file() and not audio.parent.exists()
    assert result.previous_folder == audio.parent
    assert finalize_content_name(result) == result


def test_missing_name_or_failed_summary_does_not_rename_existing_meeting(tmp_path):
    audio = recording(tmp_path)
    with patch("record_transcript_resume.pipeline.transcribe", return_value=[Segment(0, 1, "Ruído.")]), \
         patch("record_transcript_resume.pipeline.generate", return_value=SynthesisResult("", "# Sem assunto identificável")):
        result = run(audio, audio.parent, reuse_source_folder=True)
    assert result.mp3_path == audio and result.folder == audio.parent
    with patch("record_transcript_resume.pipeline.transcribe", return_value=[Segment(0, 1, "Ruído.")]), \
         patch("record_transcript_resume.pipeline.generate", return_value=SynthesisResult("nao-aplicar", "# Summary unavailable")):
        result = run(audio, audio.parent, reuse_source_folder=True)
    assert result.summary_failed and result.mp3_path == audio and result.folder == audio.parent


@pytest.mark.parametrize("name,expected", [
    ("Revisão das ações / próximos passos", "revisao-das-acoes-proximos-passos"),
    ("../../CON", "reuniao-con"), ("LPT1", "reuniao-lpt1"),
    ("...", ""), ("  .  ", ""),
])
def test_names_are_portable_and_never_paths(name, expected):
    assert safe_name(name) == expected


def test_null_name_is_not_used_as_a_file_name():
    assert _result_from_stdout('{"folder_name":null,"summary_md":"# Resumo"}').folder_name == ""


@pytest.mark.parametrize("summary", ["null", '""', "{}"])
def test_invalid_summary_does_not_provide_a_content_name(summary):
    result = _result_from_stdout('{"folder_name":"nao-aplicar","summary_md":' + summary + '}')
    assert result.folder_name == ""
    assert result.summary_md.startswith("# Summary unavailable")


@pytest.mark.parametrize("capturing", [True, False])
def test_gui_follows_paths_metadata_and_history_without_touching_active_capture(tmp_path, capturing):
    audio = recording(tmp_path)
    metadata = LibraryMetadataStore(tmp_path / "metadata.json")
    metadata.save(audio, title="Meu título", tags=("projeto",), favorite=True)
    metadata.save(audio.parent / "transcription.md", favorite=True)
    store = JobStore(tmp_path / "jobs.json")
    old_job = store.enqueue(audio, audio.parent, "pt", "small", "codex", "meeting")
    store.update(old_job.id, status="failed")
    job = store.enqueue(audio, audio.parent, "pt", "small", "codex", "meeting")
    result = process(audio, audio.parent, reuse_source_folder=True)
    active_capture = tmp_path / "current-recording.mp3" if capturing else audio
    app = SimpleNamespace(
        _library_metadata=metadata, _job_store=store, _browser_directory=audio.parent,
        _browser_history=[tmp_path, audio.parent],
        _browser_selected=BrowserEntry(audio, "audio", audio.name, "MP3", datetime.now()),
        _last_output=active_capture, _capture_in_progress=lambda:capturing,
        library_dir=Mock(),
    )
    app.library_dir.get.return_value = str(tmp_path)
    RecorderApp._apply_processed_paths(app, job, result)
    assert app._browser_directory == result.folder
    assert app._browser_selected.path == result.mp3_path
    assert app._browser_history == [tmp_path, result.folder]
    assert app._last_output == (active_capture if capturing else result.mp3_path)
    assert all(j.audio_path == result.mp3_path for j in store.list())
    saved = metadata.load()[str(result.mp3_path.resolve()).casefold()]
    assert saved["favorite"] and saved["title"] == "Meu título" and saved["tags"] == ["projeto"]
    assert metadata.load()[str((result.folder / "transcription.md").resolve()).casefold()]["favorite"]


def test_processing_again_keeps_name_without_duplicate_folder(tmp_path):
    audio = recording(tmp_path)
    first = process(audio, audio.parent, reuse_source_folder=True)
    second = process(first.mp3_path, first.folder, reuse_source_folder=True)
    assert first.folder == second.folder and first.mp3_path == second.mp3_path
    assert second.previous_folder is None
    assert recording_time(second.mp3_path) == datetime(2026, 10, 20, 9, 30)
