from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from record_transcript_resume.errors import SynthesisError
from record_transcript_resume.library import LibraryMetadataStore, browse_directory
from record_transcript_resume.meeting_topics import (
    METADATA_NAME, load_topic, normalize_topic, save_topic, summary_available,
)
from record_transcript_resume.synthesis import _result_from_stdout, generate_topic
from record_transcript_resume.synthesis import SynthesisResult
from record_transcript_resume.pipeline import run, retry_summary
from record_transcript_resume.transcription import Segment


def test_topic_is_portable_and_invalidated_when_summary_changes(tmp_path: Path):
    folder = tmp_path / "reuniao"
    folder.mkdir()
    summary = folder / "summary.md"
    summary.write_text("# Entregas\nRevisão do cronograma.", encoding="utf-8")
    save_topic(folder, "Revisão do cronograma e divisão das entregas")
    moved = folder.rename(tmp_path / "renomeada")
    assert load_topic(moved) == "Revisão do cronograma e divisão das entregas"
    (moved / "summary.md").write_text("# Novo assunto", encoding="utf-8")
    assert load_topic(moved) == ""


def test_topic_metadata_does_not_appear_in_browser(tmp_path: Path):
    (tmp_path / "summary.md").write_text("# Assunto", encoding="utf-8")
    save_topic(tmp_path, "Cronograma das entregas")
    names = [e.path.name for e in browse_directory(tmp_path, LibraryMetadataStore(tmp_path / "absent.json"))]
    assert names == ["summary.md"]


def test_old_and_failed_summaries(tmp_path: Path):
    summary = tmp_path / "summary.md"
    summary.write_text("# Reunião antiga\nDecisões salvas", encoding="utf-8")
    assert summary_available(tmp_path) and load_topic(tmp_path) == ""
    summary.write_text("# Summary unavailable\nErro", encoding="utf-8")
    assert not summary_available(tmp_path)


def test_corrupt_metadata_is_optional(tmp_path: Path):
    (tmp_path / "summary.md").write_text("# Reunião", encoding="utf-8")
    (tmp_path / METADATA_NAME).write_bytes(b"\xffbad")
    assert load_topic(tmp_path) == ""
    save_topic(tmp_path, "Acompanhamento das entregas")
    assert load_topic(tmp_path) == "Acompanhamento das entregas"


def test_topic_is_short_and_plain_text():
    assert normalize_topic(None) == ""
    assert normalize_topic('  "Revisão\n do cronograma"  ') == "Revisão do cronograma"
    assert len(normalize_topic("planejamento " * 40)) <= 100
    assert len(normalize_topic("um " * 40).split()) <= 12


def test_synthesis_accepts_new_and_legacy_payloads():
    old = _result_from_stdout('{"folder_name":"reuniao","summary_md":"# Resumo"}')
    assert old.topic == "" and old.summary_md == "# Resumo"
    new = _result_from_stdout('{"folder_name":"reuniao","summary_md":"# Resumo","topic":"Revisão das entregas"}')
    assert new.topic == "Revisão das entregas"


def test_old_meeting_generation_uses_only_saved_summary():
    with patch("record_transcript_resume.synthesis._provider_response", return_value='{"topic":"Revisão das entregas"}') as request:
        assert generate_topic("# Resumo salvo\nPrazo final sexta.", provider="claude") == "Revisão das entregas"
    prompt, provider = request.call_args.args
    assert "Prazo final sexta." in prompt and provider == "claude"
    assert "transcription.md" not in prompt


def test_invalid_topic_response_reports_failure():
    with patch("record_transcript_resume.synthesis._provider_response", return_value='{"topic":null}'):
        with pytest.raises(SynthesisError):
            generate_topic("# Resumo salvo")


def test_recording_date_is_not_changed_by_processing(tmp_path: Path):
    folder = tmp_path / "recording-20261019-093000"
    folder.mkdir()
    (folder / "recording-20261019-093000.mp3").write_bytes(b"fixture")
    (folder / "summary.md").write_text("# Processado hoje", encoding="utf-8")
    entry = browse_directory(tmp_path, LibraryMetadataStore(tmp_path / "absent.json"))[0]
    assert entry.sort_at == datetime(2026, 10, 19, 9, 30)


def test_new_processing_saves_topic_from_same_summary_call(tmp_path: Path):
    audio = tmp_path / "recording-20261020-090000.mp3"
    audio.write_bytes(b"fixture")
    response = SynthesisResult("planejamento", "# Resumo\nCronograma e entregas.", "Cronograma e divisão das entregas")
    with patch("record_transcript_resume.pipeline.transcribe", return_value=[Segment(0, 1, "Cronograma.")]), \
         patch("record_transcript_resume.pipeline.generate", return_value=response) as generate:
        result = run(audio, tmp_path)
    generate.assert_called_once()
    assert load_topic(result.folder) == response.topic
    assert not result.summary_failed


def test_retry_summary_updates_topic(tmp_path: Path):
    transcript = tmp_path / "transcription.md"
    transcript.write_text("# Transcrição\nCronograma e entregas.", encoding="utf-8")
    with patch("record_transcript_resume.pipeline.generate", return_value=SynthesisResult("", "# Resumo", "Revisão do cronograma")):
        retry_summary(transcript)
    assert load_topic(tmp_path) == "Revisão do cronograma"


def test_topic_write_failure_keeps_successful_transcript_and_summary(tmp_path: Path):
    audio = tmp_path / "recording-20261020-090000.mp3"
    audio.write_bytes(b"fixture")
    with patch("record_transcript_resume.pipeline.transcribe", return_value=[Segment(0, 1, "Cronograma.")]), \
         patch("record_transcript_resume.pipeline.generate", return_value=SynthesisResult("planejamento", "# Resumo", "Cronograma")), \
         patch("record_transcript_resume.meeting_topics.save_topic", side_effect=OSError("metadata unavailable")):
        result = run(audio, tmp_path)
    assert result.summary_path.is_file() and result.transcript_path.is_file()
    assert not result.summary_failed and result.warnings
