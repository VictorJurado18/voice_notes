from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gravador_audio.errors import TranscriptionError
from gravador_audio.pipeline import PipelineResult, run
from gravador_audio.synthesis import SynthesisResult
from gravador_audio.transcription import Segment


def _fake_segments() -> list[Segment]:
    return [Segment(start=0.0, end=2.0, text="Ola mundo.")]


def _fake_synthesis() -> SynthesisResult:
    return SynthesisResult(nome_pasta="reuniao-teste", resumo_md="# Reuniao\n\nConteudo.")


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.mp3 = Path(self.tmp) / "gravacao-20260521-120000.mp3"
        self.mp3.write_bytes(b"fake-mp3-data")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_success_creates_folder_and_files(self) -> None:
        with patch("gravador_audio.pipeline.transcribe", return_value=_fake_segments()), \
             patch("gravador_audio.pipeline.generate", return_value=_fake_synthesis()):
            result = run(self.mp3, Path(self.tmp))

        self.assertIsInstance(result, PipelineResult)
        self.assertTrue(result.folder.exists())
        self.assertEqual(result.folder.name, "reuniao-teste")
        self.assertTrue(result.mp3_path.exists())
        self.assertTrue(result.transcricao_path.exists())
        self.assertTrue(result.resumo_path.exists())
        self.assertFalse(self.mp3.exists(), "MP3 original deve ter sido movido")

    def test_run_transcricao_content(self) -> None:
        with patch("gravador_audio.pipeline.transcribe", return_value=_fake_segments()), \
             patch("gravador_audio.pipeline.generate", return_value=_fake_synthesis()):
            result = run(self.mp3, Path(self.tmp))

        content = result.transcricao_path.read_text(encoding="utf-8")
        self.assertIn("[00:00:00]", content)
        self.assertIn("Ola mundo.", content)

    def test_run_transcription_error_does_not_move_mp3(self) -> None:
        with patch("gravador_audio.pipeline.transcribe", side_effect=TranscriptionError("falha")):
            with self.assertRaises(TranscriptionError):
                run(self.mp3, Path(self.tmp))

        self.assertTrue(self.mp3.exists(), "MP3 nao deve ter sido movido quando transcricao falha")

    def test_run_synthesis_error_saves_transcricao(self) -> None:
        from gravador_audio.errors import SynthesisError
        with patch("gravador_audio.pipeline.transcribe", return_value=_fake_segments()), \
             patch("gravador_audio.pipeline.generate", side_effect=SynthesisError("falha")):
            result = run(self.mp3, Path(self.tmp))

        self.assertTrue(result.transcricao_path.exists())
        resumo = result.resumo_path.read_text(encoding="utf-8")
        self.assertIn("falhou", resumo.lower())

    def test_run_resolves_duplicate_folder_name(self) -> None:
        # Cria pasta que conflita com o nome que seria gerado
        existing = Path(self.tmp) / "reuniao-teste"
        existing.mkdir()

        with patch("gravador_audio.pipeline.transcribe", return_value=_fake_segments()), \
             patch("gravador_audio.pipeline.generate", return_value=_fake_synthesis()):
            result = run(self.mp3, Path(self.tmp))

        self.assertEqual(result.folder.name, "reuniao-teste-2")

    def test_run_calls_on_status(self) -> None:
        status_messages: list[str] = []

        with patch("gravador_audio.pipeline.transcribe", return_value=_fake_segments()), \
             patch("gravador_audio.pipeline.generate", return_value=_fake_synthesis()):
            run(self.mp3, Path(self.tmp), on_status=status_messages.append)

        self.assertIn("Transcrevendo audio...", status_messages)
        self.assertIn("Gerando resumo...", status_messages)


if __name__ == "__main__":
    unittest.main()
