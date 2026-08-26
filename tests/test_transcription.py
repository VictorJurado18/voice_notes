from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from record_transcript_resume.errors import TranscriptionError
from record_transcript_resume.transcription import Segment, assign_speakers, available_models, segments_to_markdown, transcribe


class TranscriptionTests(unittest.TestCase):
    def test_transcribe_rejects_missing_file_before_loading_model(self) -> None:
        with self.assertRaises(TranscriptionError):
            transcribe(Path("missing.mp3"))

    def test_transcribe_returns_segments(self) -> None:
        fake_seg = MagicMock()
        fake_seg.start = 0.0
        fake_seg.end = 3.5
        fake_seg.text = "  Ola mundo  "

        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([fake_seg], MagicMock())

        fake_faster_whisper = MagicMock()
        fake_faster_whisper.WhisperModel.return_value = fake_model

        with patch.object(Path, "is_file", return_value=True), \
             patch.dict("sys.modules", {"faster_whisper": fake_faster_whisper}):
            result = transcribe(Path("fake.mp3"), language="pt", model_size="small")

        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0].start, 0.0)
        self.assertAlmostEqual(result[0].end, 3.5)
        self.assertEqual(result[0].text, "Ola mundo")
        fake_model.transcribe.assert_called_once_with("fake.mp3", language="pt", vad_filter=True)

    def test_transcribe_usa_model_size_correto(self) -> None:
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([], MagicMock())
        fake_faster_whisper = MagicMock()
        fake_faster_whisper.WhisperModel.return_value = fake_model

        with patch.object(Path, "is_file", return_value=True), \
             patch.dict("sys.modules", {"faster_whisper": fake_faster_whisper}):
            transcribe(Path("fake.mp3"), language="pt", model_size="large-v3")

        fake_faster_whisper.WhisperModel.assert_called_once_with(
            "large-v3", device="cpu", compute_type="int8"
        )

    def test_transcribe_raises_on_import_error(self) -> None:
        with patch.object(Path, "is_file", return_value=True), \
             patch.dict("sys.modules", {"faster_whisper": None}):
            with self.assertRaises(TranscriptionError):
                transcribe(Path("fake.mp3"))

    def test_segments_to_markdown_formats_timestamps(self) -> None:
        segments = [
            Segment(start=0.0, end=2.0, text="Primeiro."),
            Segment(start=65.0, end=68.0, text="Segundo."),
            Segment(start=3661.0, end=3665.0, text="Terceiro."),
        ]
        result = segments_to_markdown(segments)
        lines = result.splitlines()
        self.assertEqual(lines[0], "[00:00:00] Primeiro.")
        self.assertEqual(lines[1], "[00:01:05] Segundo.")
        self.assertEqual(lines[2], "[01:01:01] Terceiro.")

    def test_segments_to_markdown_empty(self) -> None:
        result = segments_to_markdown([])
        self.assertEqual(result, "")

    def test_assign_speakers_uses_overlap_and_person_labels(self) -> None:
        segments = [Segment(0, 2, "Olá"), Segment(3, 5, "Oi"), Segment(6, 8, "Tudo bem")]
        result = assign_speakers(segments, [(0, 2, "A"), (3, 5, "B"), (6, 8, "A")])

        self.assertEqual([segment.speaker for segment in result], ["Pessoa 1", "Pessoa 2", "Pessoa 1"])
        self.assertIn("**Pessoa 1**", segments_to_markdown(result))


class AvailableModelsTests(unittest.TestCase):
    def test_retorna_todos_os_modelos_expostos_pela_interface(self) -> None:
        self.assertEqual(available_models(), ["tiny", "base", "small", "medium", "large-v3"])


if __name__ == "__main__":
    unittest.main()
