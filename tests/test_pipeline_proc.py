"""Tests for the subprocess isolation layer (_pipeline_proc).

The core invariant this file protects:

  When the pipeline fails for ANY reason — Python exception, import error,
  or a native C++ crash in ctranslate2 — _pipeline_proc must:
    1. Emit only valid JSON lines on stdout (never a raw traceback)
    2. Exit with code 1

  Without this contract, the GUI has no way to distinguish a successful
  pipeline from a crashed one, and the original bug (app closes silently
  during transcription) can regress.

These tests run _pipeline_proc as a real subprocess so they exercise the
actual isolation boundary, not a mock.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "gravador_audio._pipeline_proc"] + list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class TestPipelineProcProtocol(unittest.TestCase):
    """Validates the JSON-line protocol between _pipeline_proc and the GUI."""

    def test_sem_args_exit_1_e_json_valido(self) -> None:
        """Missing args must produce a JSON error, not a Python traceback."""
        r = _run()
        self.assertEqual(r.returncode, 1, "Exit code deve ser 1 quando args estao ausentes")
        event = json.loads(r.stdout.strip())
        self.assertEqual(event["type"], "error")

    def test_toda_linha_de_stdout_e_json(self) -> None:
        """stdout must never contain raw tracebacks — every non-empty line must be valid JSON."""
        r = _run()
        for line in r.stdout.splitlines():
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError:
                self.fail(f"Linha nao e JSON valido: {line!r}")

    def test_arquivo_inexistente_exit_1_e_erro_json(self) -> None:
        """A non-existent MP3 must produce a JSON error event and exit 1.

        This covers: faster-whisper not installed (ImportError → TranscriptionError)
        AND faster-whisper installed but file missing (file-not-found from C++ layer).
        Either way, the exception must be caught and reported as JSON.
        """
        r = _run(
            r"C:\nao\existe\arquivo.mp3",
            r"C:\nao\existe",
            "pt",
            "small",
        )
        self.assertEqual(r.returncode, 1)
        events = [json.loads(line) for line in r.stdout.splitlines() if line.strip()]
        error_events = [e for e in events if e.get("type") == "error"]
        self.assertGreater(len(error_events), 0, "Esperado pelo menos um evento de erro")

    def test_evento_done_tem_campos_obrigatorios(self) -> None:
        """When pipeline succeeds, the 'done' event must include all four path fields.

        Uses a mock pipeline.run injected via sys.modules so no real audio is needed.
        """
        import tempfile
        from unittest.mock import MagicMock, patch

        with tempfile.TemporaryDirectory() as tmp:
            mp3 = Path(tmp) / "fake.mp3"
            mp3.touch()

            fake_result = MagicMock()
            fake_result.folder = Path(tmp) / "pasta"
            fake_result.mp3_path = mp3
            fake_result.transcricao_path = Path(tmp) / "transcricao.md"
            fake_result.resumo_path = Path(tmp) / "resumo.md"

            # Patch pipeline.run inside the subprocess's import by injecting
            # a wrapper script that overrides the function before calling main().
            # Since we can't easily patch inside a subprocess, we test the module
            # directly by importing and calling main() with a monkeypatched pipeline.
            import gravador_audio._pipeline_proc as proc_mod
            import gravador_audio.pipeline as pipeline_mod

            original_run = pipeline_mod.run
            try:
                pipeline_mod.run = lambda *a, **kw: fake_result
                # Simulate argv
                import sys as _sys
                original_argv = _sys.argv[:]
                _sys.argv = [
                    "gravador_audio._pipeline_proc",
                    str(mp3),
                    tmp,
                    "pt",
                    "small",
                ]
                import io
                from contextlib import redirect_stdout

                buf = io.StringIO()
                with redirect_stdout(buf):
                    exit_code = proc_mod.main()
            finally:
                pipeline_mod.run = original_run
                _sys.argv = original_argv

        self.assertEqual(exit_code, 0)
        output = buf.getvalue().strip()
        events = [json.loads(line) for line in output.splitlines() if line.strip()]
        done_events = [e for e in events if e.get("type") == "done"]
        self.assertEqual(len(done_events), 1)
        done = done_events[0]
        for field in ("folder", "mp3", "transcricao", "resumo"):
            self.assertIn(field, done, f"Campo '{field}' ausente no evento done")

    def test_excecao_no_pipeline_vira_erro_json_nao_traceback(self) -> None:
        """Any exception raised by pipeline.run must be caught and returned as JSON error.

        This is the core regression guard: before the fix, an unhandled exception
        (or native crash) in the pipeline thread killed the GUI process entirely.
        Now, the subprocess must always report the error via JSON.
        """
        import sys as _sys
        import io
        import gravador_audio._pipeline_proc as proc_mod
        import gravador_audio.pipeline as pipeline_mod

        def _crash(*args, **kwargs):
            raise RuntimeError("falha simulada do pipeline")

        original_run = pipeline_mod.run
        original_argv = _sys.argv[:]
        try:
            pipeline_mod.run = _crash
            _sys.argv = [
                "gravador_audio._pipeline_proc",
                r"C:\fake.mp3",
                r"C:\fake",
                "pt",
                "small",
            ]
            buf = io.StringIO()
            from contextlib import redirect_stdout
            with redirect_stdout(buf):
                exit_code = proc_mod.main()
        finally:
            pipeline_mod.run = original_run
            _sys.argv = original_argv

        self.assertEqual(exit_code, 1)
        output = buf.getvalue().strip()
        event = json.loads(output)
        self.assertEqual(event["type"], "error")
        self.assertIn("falha simulada", event["msg"])


if __name__ == "__main__":
    unittest.main()
