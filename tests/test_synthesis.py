from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import patch, MagicMock

from gravador_audio.errors import SynthesisError
from gravador_audio.synthesis import SynthesisResult, generate


def _make_completed_process(stdout: str, returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.stdout = stdout
    proc.returncode = returncode
    return proc


class SynthesisTests(unittest.TestCase):
    def test_generate_returns_result_on_valid_json(self) -> None:
        payload = {
            "nome_pasta": "alinhamento-sprint",
            "resumo_md": "# Reuniao\n## Contexto\nTexto.",
        }
        proc = _make_completed_process(json.dumps(payload))

        with patch("gravador_audio.synthesis.subprocess.run", return_value=proc):
            result = generate("Transcricao de teste.", "2026-05-21")

        self.assertIsInstance(result, SynthesisResult)
        self.assertEqual(result.nome_pasta, "alinhamento-sprint")
        self.assertIn("# Reuniao", result.resumo_md)

    def test_generate_uses_fallback_on_invalid_json(self) -> None:
        proc = _make_completed_process("isso nao e json valido")

        with patch("gravador_audio.synthesis.subprocess.run", return_value=proc):
            result = generate("Transcricao.", "2026-05-21")

        self.assertEqual(result.nome_pasta, "")
        self.assertIn("falhou", result.resumo_md)

    def test_generate_strips_markdown_fences(self) -> None:
        payload = {"nome_pasta": "reuniao-produto", "resumo_md": "# Titulo"}
        fenced = f"```json\n{json.dumps(payload)}\n```"
        proc = _make_completed_process(fenced)

        with patch("gravador_audio.synthesis.subprocess.run", return_value=proc):
            result = generate("Transcricao.", "2026-05-21")

        self.assertEqual(result.nome_pasta, "reuniao-produto")

    def test_generate_raises_on_claude_not_found(self) -> None:
        with patch("gravador_audio.synthesis.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaises(SynthesisError):
                generate("Transcricao.", "2026-05-21")

    def test_generate_raises_on_timeout(self) -> None:
        with patch(
            "gravador_audio.synthesis.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=120),
        ):
            with self.assertRaises(SynthesisError):
                generate("Transcricao.", "2026-05-21")


if __name__ == "__main__":
    unittest.main()
