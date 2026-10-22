from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from record_transcript_resume.errors import SynthesisError, TranscriptionError
from record_transcript_resume.pipeline import PipelineResult, retry_summary, run
from record_transcript_resume.synthesis import SynthesisResult
from record_transcript_resume.transcription import Segment


def _fake_segments() -> list[Segment]:
    return [Segment(start=0.0, end=2.0, text="Hello world.")]


def _fake_synthesis() -> SynthesisResult:
    return SynthesisResult(folder_name="test-meeting", summary_md="# Meeting\n\nContent.")


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.mp3 = Path(self.tmp) / "recording-20260521-120000.mp3"
        self.mp3.write_bytes(b"fake-mp3-data")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_success_creates_folder_and_files(self) -> None:
        with patch("record_transcript_resume.pipeline.transcribe", return_value=_fake_segments()), \
             patch("record_transcript_resume.pipeline.generate", return_value=_fake_synthesis()):
            result = run(self.mp3, Path(self.tmp))

        self.assertIsInstance(result, PipelineResult)
        self.assertTrue(result.folder.exists())
        self.assertEqual(result.folder.name, "test-meeting")
        self.assertTrue(result.mp3_path.exists())
        self.assertTrue(result.transcript_path.exists())
        self.assertTrue(result.summary_path.exists())
        self.assertFalse(self.mp3.exists(), "Original MP3 should have been moved")

    def test_run_transcript_content(self) -> None:
        with patch("record_transcript_resume.pipeline.transcribe", return_value=_fake_segments()), \
             patch("record_transcript_resume.pipeline.generate", return_value=_fake_synthesis()):
            result = run(self.mp3, Path(self.tmp))

        content = result.transcript_path.read_text(encoding="utf-8")
        self.assertIn("[00:00:00]", content)
        self.assertIn("Hello world.", content)

    def test_run_transcription_error_does_not_move_mp3(self) -> None:
        with patch("record_transcript_resume.pipeline.transcribe", side_effect=TranscriptionError("failure")):
            with self.assertRaises(TranscriptionError):
                run(self.mp3, Path(self.tmp))

        self.assertTrue(self.mp3.exists(), "MP3 must not be moved when transcription fails")

    def test_import_copies_media_into_library_without_moving_original(self) -> None:
        destination = Path(self.tmp) / "library"
        with patch("record_transcript_resume.pipeline.transcribe", return_value=_fake_segments()), \
             patch("record_transcript_resume.pipeline.generate", return_value=_fake_synthesis()):
            result = run(self.mp3, destination, preserve_source=True)

        self.assertTrue(self.mp3.is_file())
        self.assertTrue(result.mp3_path.is_file())
        self.assertNotEqual(result.mp3_path, self.mp3)
        self.assertEqual(result.mp3_path.read_bytes(), self.mp3.read_bytes())

    def test_run_synthesis_error_saves_transcript(self) -> None:
        from record_transcript_resume.errors import SynthesisError
        with patch("record_transcript_resume.pipeline.transcribe", return_value=_fake_segments()), \
             patch("record_transcript_resume.pipeline.generate", side_effect=SynthesisError("failure")):
            result = run(self.mp3, Path(self.tmp))

        self.assertTrue(result.transcript_path.exists())
        summary = result.summary_path.read_text(encoding="utf-8")
        self.assertIn("unavailable", summary.lower())
        self.assertIn("codex", summary.lower())
        self.assertTrue(result.summary_failed)
        self.assertTrue(result.warnings)

    def test_summary_only_failure_keeps_transcript_for_retry(self) -> None:
        with patch("record_transcript_resume.pipeline.transcribe", return_value=_fake_segments()), \
             patch("record_transcript_resume.pipeline.generate", side_effect=SynthesisError("login required")):
            result = run(self.mp3, Path(self.tmp), output_mode="summary")

        self.assertTrue(result.summary_failed)
        self.assertTrue(result.transcript_path.is_file())

    def test_run_resolves_duplicate_folder_name(self) -> None:
        existing = Path(self.tmp) / "test-meeting"
        existing.mkdir()

        with patch("record_transcript_resume.pipeline.transcribe", return_value=_fake_segments()), \
             patch("record_transcript_resume.pipeline.generate", return_value=_fake_synthesis()):
            result = run(self.mp3, Path(self.tmp))

        self.assertEqual(result.folder.name, "test-meeting-2")

    def test_process_recording_renames_folder_and_audio_without_nesting(self) -> None:
        folder = Path(self.tmp) / "recording-20260521-120000"
        folder.mkdir()
        audio = folder / self.mp3.name
        self.mp3.replace(audio)
        with patch("record_transcript_resume.pipeline.transcribe", return_value=_fake_segments()), \
             patch("record_transcript_resume.pipeline.generate", return_value=_fake_synthesis()):
            result = run(audio, folder, reuse_source_folder=True)

        self.assertEqual(result.folder, folder.with_name("test-meeting"))
        self.assertEqual(result.mp3_path, result.folder / "test-meeting.mp3")
        self.assertEqual(result.previous_folder, folder)
        self.assertTrue(result.mp3_path.is_file())
        self.assertTrue((result.folder / "transcription.md").is_file())
        self.assertTrue((result.folder / "summary.md").is_file())
        self.assertFalse(folder.exists())

    def test_fallback_folder_uses_audio_stem_once(self) -> None:
        with patch("record_transcript_resume.pipeline.transcribe", return_value=_fake_segments()), \
             patch("record_transcript_resume.pipeline.generate", side_effect=SynthesisError("offline")):
            result = run(self.mp3, Path(self.tmp))

        self.assertEqual(result.folder.name, self.mp3.stem)

    def test_run_sanitizes_model_folder_name(self) -> None:
        unsafe = SynthesisResult(folder_name="../Meeting: Q3 / Review", summary_md="# Meeting")
        with patch("record_transcript_resume.pipeline.transcribe", return_value=_fake_segments()), \
             patch("record_transcript_resume.pipeline.generate", return_value=unsafe):
            result = run(self.mp3, Path(self.tmp))

        self.assertEqual(result.folder.parent, Path(self.tmp))
        self.assertEqual(result.folder.name, "meeting-q3-review")

    def test_run_calls_on_status(self) -> None:
        status_messages: list[str] = []

        with patch("record_transcript_resume.pipeline.transcribe", return_value=_fake_segments()), \
             patch("record_transcript_resume.pipeline.generate", return_value=_fake_synthesis()):
            run(self.mp3, Path(self.tmp), on_status=status_messages.append)

        self.assertIn("Transcribing audio...", status_messages)
        self.assertIn("Generating summary...", status_messages)

    def test_run_passes_selected_summary_template(self) -> None:
        with patch("record_transcript_resume.pipeline.transcribe", return_value=_fake_segments()), \
             patch("record_transcript_resume.pipeline.generate", return_value=_fake_synthesis()) as generate:
            run(self.mp3, Path(self.tmp), summary_template="class")

        self.assertEqual(generate.call_args.kwargs["summary_template"], "class")

    def test_run_passes_meeting_specific_instructions_to_summary(self) -> None:
        with patch("record_transcript_resume.pipeline.transcribe", return_value=_fake_segments()), \
             patch("record_transcript_resume.pipeline.generate", return_value=_fake_synthesis()) as generate:
            run(self.mp3, Path(self.tmp), additional_instructions="Realce decisões e riscos.")

        self.assertEqual(generate.call_args.kwargs["additional_instructions"], "Realce decisões e riscos.")

    def test_transcription_only_skips_provider_and_does_not_save_summary(self) -> None:
        with patch("record_transcript_resume.pipeline.transcribe", return_value=_fake_segments()), \
             patch("record_transcript_resume.pipeline.generate") as generate:
            result = run(self.mp3, Path(self.tmp), output_mode="transcription")

        generate.assert_not_called()
        self.assertIsNotNone(result.transcript_path)
        self.assertIsNone(result.summary_path)
        self.assertTrue(result.transcript_path.exists())

    def test_summary_only_does_not_save_transcription(self) -> None:
        with patch("record_transcript_resume.pipeline.transcribe", return_value=_fake_segments()), \
             patch("record_transcript_resume.pipeline.generate", return_value=_fake_synthesis()):
            result = run(self.mp3, Path(self.tmp), output_mode="summary")

        self.assertIsNone(result.transcript_path)
        self.assertIsNotNone(result.summary_path)
        self.assertTrue(result.summary_path.exists())

    def test_run_adds_speaker_labels_when_enabled(self) -> None:
        with patch("record_transcript_resume.pipeline.transcribe", return_value=_fake_segments()), \
             patch("record_transcript_resume.diarization.diarize", return_value=[(0, 2, "speaker_a")]), \
             patch("record_transcript_resume.pipeline.generate", return_value=_fake_synthesis()) as generate:
            run(self.mp3, Path(self.tmp), diarize_speakers=True, huggingface_token="hf_test")

        self.assertIn("**Pessoa 1**", generate.call_args.args[0])

    def test_diarization_failure_keeps_transcription_and_summary(self) -> None:
        statuses: list[str] = []
        with patch("record_transcript_resume.pipeline.transcribe", return_value=_fake_segments()), \
             patch("record_transcript_resume.diarization.diarize", side_effect=TranscriptionError("modelo indisponível")), \
             patch("record_transcript_resume.pipeline.generate", return_value=_fake_synthesis()):
            result = run(
                self.mp3, Path(self.tmp), diarize_speakers=True, huggingface_token="hf_test",
                on_status=statuses.append,
            )

        self.assertTrue(result.transcript_path.exists())
        self.assertTrue(result.summary_path.exists())
        self.assertEqual(result.warnings, ("Não foi possível separar os falantes; a transcrição continuou sem identificá-los.",))
        self.assertIn(result.warnings[0], statuses)

    def test_retry_summary_reuses_transcription_without_touching_mp3(self) -> None:
        folder = Path(self.tmp) / "saved-meeting"
        folder.mkdir()
        mp3_path = folder / "recording.mp3"
        mp3_path.write_bytes(b"original-audio")
        transcript_path = folder / "transcription.md"
        transcript_path.write_text("# Transcription\n\nAlready transcribed text.", encoding="utf-8")
        previous_summary = folder / "summary.md"
        previous_summary.write_text("# Summary unavailable\n", encoding="utf-8")

        with patch("record_transcript_resume.pipeline.generate", return_value=_fake_synthesis()) as generate:
            summary_path = retry_summary(transcript_path, provider="claude")

        self.assertEqual(summary_path, previous_summary)
        self.assertEqual(mp3_path.read_bytes(), b"original-audio")
        self.assertIn("Already transcribed text.", generate.call_args.args[0])
        self.assertNotIn("# Transcription", generate.call_args.args[0])
        self.assertEqual(generate.call_args.kwargs["provider"], "claude")
        self.assertEqual(summary_path.read_text(encoding="utf-8"), "# Meeting\n\nContent.\n")

    def test_retry_summary_preserves_previous_summary_when_provider_fails(self) -> None:
        folder = Path(self.tmp) / "saved-meeting"
        folder.mkdir()
        transcript_path = folder / "transcription.md"
        transcript_path.write_text("# Transcription\n\nSaved text.", encoding="utf-8")
        summary_path = folder / "summary.md"
        summary_path.write_text("# Existing summary\n", encoding="utf-8")

        with patch("record_transcript_resume.pipeline.generate", side_effect=SynthesisError("login required")):
            with self.assertRaises(SynthesisError):
                retry_summary(transcript_path)

        self.assertEqual(summary_path.read_text(encoding="utf-8"), "# Existing summary\n")


if __name__ == "__main__":
    unittest.main()
