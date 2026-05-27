from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from gravador_audio.errors import TranscriptionError
from gravador_audio.transcription import Segment, segments_to_markdown, transcribe


class TranscriptionTests(unittest.TestCase):
    def test_transcribe_returns_segments(self) -> None:
        fake_seg = MagicMock()
        fake_seg.start = 0.0
        fake_seg.end = 3.5
        fake_seg.text = "  Ola mundo  "

        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([fake_seg], MagicMock())

        fake_faster_whisper = MagicMock()
        fake_faster_whisper.WhisperModel.return_value = fake_model

        with patch.dict("sys.modules", {"faster_whisper": fake_faster_whisper}):
            result = transcribe(Path("fake.mp3"), language="pt")

        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0].start, 0.0)
        self.assertAlmostEqual(result[0].end, 3.5)
        self.assertEqual(result[0].text, "Ola mundo")

    def test_transcribe_raises_on_import_error(self) -> None:
        with patch.dict("sys.modules", {"faster_whisper": None}):
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


if __name__ == "__main__":
    unittest.main()
